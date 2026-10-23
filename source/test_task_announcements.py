"""Local task results use the speech pipeline without a model or desktop IO."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from providers.engine_pipeline import PipelineEngine


class FakeLLM:
    caps = {}

    def __init__(self):
        self.calls = []

    async def chat(self, messages, tools):
        self.calls.append(messages)
        yield {"text": "Here is the requested answer."}


class FakeVoice:
    def __init__(self):
        self.spoken = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()

    async def speak(self, text, **kwargs):
        self.spoken.append(text)
        self.entered.set()
        await self.release.wait()
        yield b"\0\0" * 16


async def until(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(0.005)
    await asyncio.wait_for(wait(), 2)


class Announcements(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.llm = FakeLLM()
        self.voice = FakeVoice()
        self.engine = PipelineEngine(self.llm, tts=self.voice)

    async def asyncTearDown(self):
        await self.engine.close()
        await asyncio.sleep(0)

    async def test_result_is_assistant_only_and_emits_speech_without_model(self):
        await self.engine.announce("  YouTube\n is open in a browser tab.  ")
        self.assertEqual(self.llm.calls, [])
        self.assertEqual(self.voice.spoken, ["YouTube is open in a browser tab."])
        self.assertEqual(self.engine._history, [{"role": "assistant", "content": self.voice.spoken[0]}])
        messages = []
        while not self.engine._queue.empty():
            messages.append(self.engine._queue.get_nowait())
        self.assertTrue(any(message.data for message in messages))
        self.assertTrue(any(message.server_content and message.server_content.output_transcription for message in messages))
        self.assertTrue(messages[-1].server_content.turn_complete)

    async def test_waits_for_active_generation_and_tool_results(self):
        active_release = asyncio.Event()
        self.engine._gen = asyncio.create_task(active_release.wait())
        self.engine._awaiting = {"launch": "open_app"}
        task = asyncio.create_task(self.engine.announce("Notepad is open."))
        await asyncio.sleep(0.05)
        self.assertFalse(self.voice.spoken)
        active_release.set()
        await self.engine._gen
        await asyncio.sleep(0.05)
        self.assertFalse(self.voice.spoken)
        self.engine._awaiting.clear()
        await asyncio.wait_for(task, 2)
        self.assertEqual(self.voice.spoken, ["Notepad is open."])

    async def test_commands_during_announcement_queue_after_its_speech(self):
        self.voice.release.clear()
        task = asyncio.create_task(self.engine.announce("Notepad is open."))
        await self.voice.entered.wait()
        await self.engine.send_client_content(turns={"role": "user", "parts": [{"text": "Explain gravity briefly"}]})
        self.assertEqual(self.llm.calls, [])
        self.assertEqual(len(self.engine._pending_inputs), 1)
        self.voice.release.set()
        await task
        await until(lambda: len(self.voice.spoken) == 2)
        await until(lambda: self.engine._gen.done())
        self.assertEqual(self.voice.spoken, ["Notepad is open.", "Here is the requested answer."])
        self.assertEqual([m["role"] for m in self.engine._history], ["assistant", "user", "assistant"])
        self.assertEqual(len(self.llm.calls), 1)

    async def test_multiple_announcements_do_not_interleave(self):
        self.voice.release.clear()
        first = asyncio.create_task(self.engine.announce("First app is open."))
        await self.voice.entered.wait()
        second = asyncio.create_task(self.engine.announce("Second app is open."))
        await asyncio.sleep(0.05)
        self.assertEqual(self.voice.spoken, ["First app is open."])
        self.voice.release.set()
        await asyncio.gather(first, second)
        self.assertEqual(self.voice.spoken, ["First app is open.", "Second app is open."])

    async def test_interrupt_discards_waiting_notice(self):
        self.engine._awaiting = {"launch": "open_app"}
        task = asyncio.create_task(self.engine.announce("This should not be said."))
        await asyncio.sleep(0.05)
        self.engine.interrupt()
        self.engine._awaiting.clear()
        await asyncio.wait_for(task, 2)
        self.assertFalse(self.voice.spoken)

    async def test_interrupt_cancels_active_notice(self):
        self.voice.release.clear()
        task = asyncio.create_task(self.engine.announce("Notepad is open."))
        await self.voice.entered.wait()
        self.engine.interrupt()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIsNone(self.engine._gen)

    async def test_close_discards_waiting_and_future_notices(self):
        self.engine._awaiting = {"launch": "open_app"}
        task = asyncio.create_task(self.engine.announce("Waiting notice."))
        await asyncio.sleep(0.05)
        await self.engine.close()
        await asyncio.wait_for(task, 2)
        await self.engine.announce("Closed notice.")
        self.assertFalse(self.voice.spoken)


class PluginAnnouncements(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from main import JarvisLive
        self.owner = JarvisLive.__new__(JarvisLive)
        self.owner.ui = SimpleNamespace(write_log=Mock())
        self.owner._loop = asyncio.get_running_loop()
        self.owner.session = SimpleNamespace(announce=AsyncMock(), send_client_content=AsyncMock())

    async def test_completion_dispatches_local_announcement(self):
        self.owner.plugin_say("[JARVIS_TASK_RESULT]Notepad is open.")
        await until(lambda: self.owner.session.announce.await_count == 1)
        self.owner.session.announce.assert_awaited_once_with("Notepad is open.")
        self.owner.session.send_client_content.assert_not_called()
        self.owner.ui.write_log.assert_not_called()

    async def test_ordinary_plugin_instruction_keeps_existing_route(self):
        self.owner.plugin_say("Give a short status report.")
        await until(lambda: self.owner.session.send_client_content.await_count == 1)
        self.owner.session.announce.assert_not_called()
        self.owner.session.send_client_content.assert_awaited_once_with(
            turns={"role": "user", "parts": [{"text": "Give a short status report."}]}, turn_complete=True)

    async def test_disconnected_completion_still_appears_in_chat(self):
        self.owner.session = None
        self.owner.plugin_say("[JARVIS_TASK_RESULT]Could not confirm Notepad opened.")
        self.owner.ui.write_log.assert_called_once_with("JARVIS: Could not confirm Notepad opened.")

    async def test_engine_without_announce_never_receives_fake_user_result(self):
        self.owner.session = SimpleNamespace(send_client_content=AsyncMock())
        self.owner.plugin_say("[JARVIS_TASK_RESULT]Notepad is open.")
        self.owner.ui.write_log.assert_called_once_with("JARVIS: Notepad is open.")
        self.owner.session.send_client_content.assert_not_called()

    async def test_failed_scheduling_closes_coroutine_and_logs_completion(self):
        with patch("main.asyncio.run_coroutine_threadsafe", side_effect=RuntimeError("loop stopped")):
            self.owner.plugin_say("[JARVIS_TASK_RESULT]Notepad is open.")
        self.owner.ui.write_log.assert_called_once_with("JARVIS: Notepad is open.")


if __name__ == "__main__":
    unittest.main()
