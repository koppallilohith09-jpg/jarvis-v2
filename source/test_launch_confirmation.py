"""Window confirmation regression tests; no real desktop reads or launches."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from actions import open_app as action
from core import launch_confirmation as confirmation


class WindowEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.identity = confirmation.Identity('Notepad', frozenset({'notepad'}))
        self.window = confirmation.Window(100, confirmation.Process(12, 'notepad.exe'), 'Private note')

    def wait(self, windows, before=(), timeout=.31):
        now = [0.0]
        return confirmation.wait_for_window(
            self.identity, before, timeout=timeout, poll=.1,
            read_windows=lambda: windows,
            clock=lambda: now[0], sleep=lambda delay: now.__setitem__(0, now[0] + delay))

    def test_new_visible_window_confirms_after_two_samples(self):
        result = self.wait((self.window,))
        self.assertTrue(result.verified)
        self.assertEqual(result.evidence, 'exact_process_name')

    def test_background_pid_is_not_window_evidence(self):
        self.assertFalse(self.wait(()).verified)

    def test_hidden_cloaked_tool_tray_and_minimized_windows_do_not_confirm(self):
        for properties in ({'visible': False}, {'cloaked': True}, {'tool_window': True},
                           {'minimized': True}, {'window_class': 'Shell_TrayWnd'},
                           {'width': 5}, {'title': ''}):
            with self.subTest(properties=properties):
                self.assertFalse(self.wait((replace(self.window, **properties),)).verified)

    def test_same_process_with_new_window_can_confirm(self):
        before = (replace(self.window, hwnd=99),)
        self.assertTrue(self.wait((self.window,), before).verified)

    def test_existing_window_restore_or_foreground_change_can_confirm(self):
        self.assertTrue(self.wait((self.window,), (replace(self.window, minimized=True),)).verified)
        self.assertTrue(self.wait((replace(self.window, foreground=True),), (self.window,)).verified)

    def test_unchanged_existing_window_cannot_prove_launch(self):
        result = self.wait((self.window,), (self.window,))
        self.assertFalse(result.verified)
        self.assertIn('existing window', result.reason)

    def test_transient_splash_needs_stable_second_observation(self):
        now = [0.0]
        calls = [0]
        def read():
            calls[0] += 1
            return (self.window,) if calls[0] == 1 else ()
        result = confirmation.wait_for_window(self.identity, (), timeout=.31, poll=.1,
            read_windows=read, clock=lambda: now[0],
            sleep=lambda delay: now.__setitem__(0, now[0] + delay))
        self.assertFalse(result.verified)

    def test_similar_process_or_misleading_window_title_never_match(self):
        for name in ('notepadplus.exe', 'msedgewebview2.exe', 'password.exe'):
            window = replace(self.window, process=confirmation.Process(12, name), title='Notepad')
            self.assertFalse(self.identity.evidence(window))

    def test_store_identity_can_come_from_applicationframehost_child(self):
        identity = confirmation.Identity('Example', frozenset({'example'}), app_ids=frozenset({'vendor.example!app'}))
        window = replace(self.window,
            process=confirmation.Process(25, 'ApplicationFrameHost.exe'),
            children=(confirmation.Process(26, 'actual.exe', app_id='Vendor.Example!App'),))
        self.assertEqual(identity.evidence(window), 'registered_app_id')
        self.assertEqual(confirmation.candidates(identity, (window,)), [window])

    def test_installed_path_wins_over_ambiguous_same_named_process(self):
        first = replace(self.window, process=confirmation.Process(12, 'editor.exe', r'C:\One\editor.exe'))
        second = replace(self.window, hwnd=101, process=confirmation.Process(13, 'editor.exe', r'C:\Two\editor.exe'))
        ambiguous = confirmation.Identity('Editor', frozenset({'editor'}))
        self.assertEqual(confirmation.candidates(ambiguous, (first, second)), [])
        known = replace(ambiguous, paths=frozenset({r'c:\one\editor.exe'}))
        self.assertEqual(confirmation.candidates(known, (first, second)), [first])

    def test_generic_shortcut_host_is_not_application_identity(self):
        identity = confirmation.Identity('Web app', frozenset({'webapp'}), paths=frozenset({r'c:\windows\explorer.exe'}))
        window = replace(self.window, process=confirmation.Process(1, 'explorer.exe', r'C:\Windows\explorer.exe'))
        self.assertFalse(identity.evidence(window))

    def test_access_denied_reports_unverified_without_private_exception(self):
        result = confirmation.wait_for_window(self.identity, (), read_windows=Mock(side_effect=PermissionError('private title')))
        self.assertFalse(result.verified)
        self.assertNotIn('private', result.reason)

    def test_identity_resolves_alias_installed_path_and_store_app(self):
        with patch('core.windows_launcher.index', return_value={'notepad': ('exe', r'C:\Apps\notepad.exe')}), \
             patch('shutil.which', return_value=None):
            result = confirmation.resolve_identity('notepad', 'notepad.exe')
        self.assertIn('notepad', result.names)
        self.assertIn(r'c:\apps\notepad.exe', result.paths)
        with patch('core.windows_launcher.index', return_value={'example': ('store', 'Vendor.Example!App')}), \
             patch('shutil.which', return_value=None):
            result = confirmation.resolve_identity('Example')
        self.assertIn('vendor.example!app', result.app_ids)


class LaunchAnnouncementTests(unittest.TestCase):
    def setUp(self):
        self.player = SimpleNamespace(write_log=Mock(), request_say=Mock())
        self.identity = confirmation.Identity('Notepad', frozenset({'notepad'}))
        self.window = confirmation.Window(100, confirmation.Process(12, 'notepad.exe'), 'Private note', foreground=True)

    def test_already_foreground_reports_verified_without_relaunching(self):
        launch = Mock()
        with patch.object(action, '_SYSTEM', 'Windows'), \
             patch.object(action, '_LAUNCHERS', {'Windows': launch}), \
             patch.object(confirmation, 'resolve_identity', return_value=self.identity), \
             patch.object(confirmation, 'snapshot', return_value=(self.window,)):
            action._launch_and_verify(self.player, 'Notepad', 'notepad.exe')
        launch.assert_not_called()
        self.player.request_say.assert_called_once_with('[JARVIS_TASK_RESULT]Notepad is already open and in front.')
        self.assertTrue(all(call.args[0].startswith('SYS: ') for call in self.player.write_log.call_args_list))
        self.assertNotIn('Private', str(self.player.request_say.call_args))

    def test_focus_return_alone_is_not_success(self):
        launch = Mock(return_value=True)
        window = replace(self.window, foreground=False)
        with patch.object(action, '_SYSTEM', 'Windows'), \
             patch.object(action, '_LAUNCHERS', {'Windows': launch}), \
             patch.object(confirmation, 'resolve_identity', return_value=self.identity), \
             patch.object(confirmation, 'snapshot', return_value=(window,)), \
             patch.object(confirmation, 'focus_window', return_value=True), \
             patch.object(confirmation, 'wait_for_window', return_value=confirmation.Confirmation(False, reason='No window appeared.')):
            action._launch_and_verify(self.player, 'Notepad', 'notepad.exe')
        launch.assert_called_once()
        self.assertIn('could not confirm', self.player.request_say.call_args.args[0])
        self.assertNotIn('is open.', self.player.request_say.call_args.args[0])

    def test_success_uses_literal_completion_callback(self):
        launch = Mock(return_value=True)
        with patch.object(action, '_SYSTEM', 'Windows'), \
             patch.object(action, '_LAUNCHERS', {'Windows': launch}), \
             patch.object(confirmation, 'resolve_identity', return_value=self.identity), \
             patch.object(confirmation, 'snapshot', return_value=()), \
             patch.object(confirmation, 'wait_for_window', return_value=confirmation.Confirmation(True, window=self.window)):
            action._launch_and_verify(self.player, 'Notepad', 'notepad.exe')
        self.player.request_say.assert_called_once_with('[JARVIS_TASK_RESULT]Notepad is open.')

    def test_launch_rejection_is_announced_as_failure(self):
        with patch.object(action, '_SYSTEM', 'Windows'), \
             patch.object(action, '_LAUNCHERS', {'Windows': Mock(return_value=False)}), \
             patch.object(confirmation, 'resolve_identity', return_value=self.identity), \
             patch.object(confirmation, 'snapshot', return_value=()):
            action._launch_and_verify(self.player, 'Notepad', 'notepad.exe')
        self.assertIn('I could not open Notepad', self.player.request_say.call_args.args[0])

    def test_no_callback_or_broken_callback_still_displays_final_result(self):
        for callback in (None, Mock(side_effect=RuntimeError('disconnected'))):
            player = SimpleNamespace(write_log=Mock(), request_say=callback)
            action._announce(player, 'Notepad is open.')
            self.assertIn('JARVIS: Notepad is open.', [call.args[0] for call in player.write_log.call_args_list])

    def test_open_returns_started_and_defers_all_window_reads(self):
        worker = Mock()
        with patch.object(action, '_SYSTEM', 'Windows'), \
             patch.object(action.threading, 'Thread', return_value=worker), \
             patch.object(confirmation, 'snapshot') as snapshot:
            result = action.open_app({'app_name': 'Notepad'}, player=self.player)
        self.assertIn('status=started', result)
        snapshot.assert_not_called()
        worker.start.assert_called_once()


if __name__ == '__main__':
    unittest.main()
