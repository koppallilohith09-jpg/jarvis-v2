import asyncio,os,unittest
from types import SimpleNamespace
from unittest.mock import Mock

class VoiceReceiver(unittest.IsolatedAsyncioTestCase):
    async def test_heard_and_reply_are_visible_before_turn_complete(self):
        from main import JarvisLive
        from providers.base import Msg
        owner=JarvisLive.__new__(JarvisLive)
        owner.ui=Mock();owner._clear_stall=Mock();owner._visemes=Mock();owner._interrupted=False
        owner._last_user_speech=0;owner._last_out_logged='';owner._asst_name='JARVIS';owner._session_log=[]
        owner._dashboard=None;owner._vision_close_pending=False;owner._turn_done_event=asyncio.Event()
        heard=asyncio.Event();reply=asyncio.Event();finish=asyncio.Event()
        async def receive():
            yield Msg.heard('open youtube');heard.set();await reply.wait()
            yield Msg.said('Opening YouTube.');finish.set();await asyncio.Event().wait()
        owner.session=SimpleNamespace(receive=receive)
        task=asyncio.create_task(owner._receive_audio())
        try:
            await asyncio.wait_for(heard.wait(),2)
            owner.ui.live_transcript.assert_any_call('you','open youtube');owner.ui.write_log.assert_not_called()
            reply.set();await asyncio.wait_for(finish.wait(),2)
            owner.ui.live_transcript.assert_any_call('jarvis','Opening YouTube.');owner.ui.write_log.assert_not_called()
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task

class VoiceUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ['QT_QPA_PLATFORM']='offscreen';os.environ['JARVIS_OFFSCREEN_STATIC']='1'
        from PyQt6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication(['voice-test'])
    def test_live_bubble_updates_and_final_log_does_not_duplicate(self):
        from core.unified_shell import ChatFeed
        shell=SimpleNamespace(operation=Mock(),events=[]);chat=ChatFeed(shell)
        before=len(chat.bubbles);chat.live_transcript('you','open youtube');self.assertEqual(len(chat.bubbles),before+1)
        chat.append_log('You: open youtube');self.assertEqual(len(chat.bubbles),before+1)
        chat.live_transcript('jarvis','Opening');chat.live_transcript('jarvis','Opening YouTube.')
        chat.append_log('JARVIS: Opening YouTube.');self.assertEqual(len(chat.bubbles),before+2);self.assertEqual(chat.live,{})
        chat.live_transcript('jarvis','Partial reply');chat.live_transcript('end','');self.assertEqual(chat.live,{})
        chat.close()
    def test_hold_button_unmutes_and_delivers_press_and_release(self):
        from core.unified_shell import UnifiedShell
        window=SimpleNamespace(_muted=True,_ptt_hold=Mock())
        window._toggle_mute=lambda:setattr(window,'_muted',False)
        shell=SimpleNamespace(window=window,talk=Mock(),operation=Mock())
        UnifiedShell.hold_to_talk(shell,True);self.assertFalse(window._muted)
        UnifiedShell.hold_to_talk(shell,False)
        self.assertEqual([c.args for c in window._ptt_hold.call_args_list],[(True,),(False,)])

if __name__=='__main__':unittest.main()
