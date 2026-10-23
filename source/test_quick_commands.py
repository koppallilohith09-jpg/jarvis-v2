import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock
from core.quick_commands import parse,result_line
from core.audio_queue import put_latest
from providers.engine_pipeline import PipelineEngine

class ParseTests(unittest.TestCase):
    def test_websites_never_become_app_search(self):
        for text in ('open youtube','Hey Jarvis, please open YouTube','could you open youtube please','go to youtube.com'):
            plan=parse(text);self.assertEqual(plan['name'],'browser_control');self.assertIn('youtube.com',plan['args']['url'])
    def test_ambiguous_open_asks(self):
        for text in ('open','open it','open the app'):self.assertIn('reply',parse(text))
    def test_compound_or_descriptive_sentences_fall_through(self):
        for text in ('explain how to open youtube','open notepad and type hello','open notepad; shutdown','opening youtube is easy'):
            self.assertIsNone(parse(text))
    def test_result_honesty(self):
        plan={'label':'Notepad'}
        self.assertEqual(result_line(plan,'status=started action=open_app'),'Opening Notepad.')
        self.assertIn('could not',result_line(plan,'status=failed action=open_app reason="Not installed"'))
        self.assertIn('Not installed',result_line(plan,'status=failed action=open_app reason="Not installed"'))
    def test_queue_keeps_recent_without_overflow(self):
        q=asyncio.Queue(maxsize=2)
        for i in range(100):put_latest(q,i)
        self.assertEqual([q.get_nowait(),q.get_nowait()],[98,99])
    def test_result_distinguishes_tab_from_loaded_page(self):
        plan={'label':'YouTube'}
        self.assertEqual(result_line(plan,'status=done evidence=browser_tab_url load_verified=false'),
                         'YouTube is open in a browser tab.')
        self.assertEqual(result_line(plan,{'status':'done','evidence':'page_loaded','load_verified':True}),
                         'YouTube has loaded.')
        self.assertNotIn('has loaded',result_line(plan,{'status':'done','evidence':'page_loaded','load_verified':False}))
    def test_tool_advisory_is_not_spoken(self):
        text=result_line({'label':'YouTube'},'status=unverified reason="No matching tab" -- NOT confirmed. Tell the user what to check.')
        self.assertIn('No matching tab',text)
        self.assertNotIn('Tell the user',text)
    def test_redirect_does_not_claim_requested_page_loaded(self):
        text=result_line({'label':'YouTube'},{'status':'done','redirected':True,'opened':'https://login.example.com/'})
        self.assertIn('redirected to https://login.example.com/',text)
        self.assertNotIn('has loaded',text)
    def test_unmatched_tool_quotes_do_not_break_response_receiver(self):
        plan={'label':"Reader's app"}
        self.assertIn('Opening',result_line(plan,"status=started action=open_app app=Reader's app -- UNDER WAY"))
        self.assertIn('could not confirm',result_line({'label':'YouTube'},'status=unverified action=browser_control reason="the browser status was truncated'))
    def test_windows_launch_never_types(self):
        from core import windows_launcher
        with patch.object(windows_launcher.shutil,'which',return_value=None),patch.object(windows_launcher,'index',return_value={}),patch.object(windows_launcher.subprocess,'run',return_value=SimpleNamespace(stdout='[]')):
            self.assertFalse(windows_launcher.launch('Unknown app'))
        with patch.object(windows_launcher.shutil,'which',return_value='C:/Windows/notepad.exe'),patch.object(windows_launcher.subprocess,'Popen') as launch:
            self.assertTrue(windows_launcher.launch('notepad'));launch.assert_called_once()
    def test_disconnected_provider_can_route_direct_commands(self):
        from providers.llm_cloud_setup import CloudSetup
        self.assertTrue(CloudSetup.caps['tools'])
        self.assertEqual(parse('open youtube')['name'],'browser_control')

class FakeLLM:
    caps={'tools':True,'tool_format':'openai'}
    def __init__(self):self.calls=0
    async def chat(self,*args):
        self.calls+=1
        raise AssertionError('Quick command must not ask the model.')
        yield {}

def engine():
    tools=[{'name':name,'description':'Test tool','parameters':{'type':'OBJECT','properties':{}}} for name in ('browser_control','open_app')]
    return PipelineEngine(FakeLLM(),config=SimpleNamespace(system_instruction='',tools=[{'function_declarations':tools}]))

class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_open_and_tool_reply_skip_both_model_rounds(self):
        e=engine();await e.send_client_content(turns={'parts':[{'text':'open youtube'}]})
        message=await asyncio.wait_for(e._queue.get(),1)
        call=message.tool_call.function_calls[0]
        self.assertEqual(call.name,'browser_control');self.assertEqual(e._llm.calls,0)
        await e.send_tool_response(function_responses=[SimpleNamespace(id=call.id,name=call.name,response={'result':'Opened https://www.youtube.com in browser'})])
        await e._gen
        reply=await e._queue.get();self.assertIn('browser',reply.server_content.output_transcription.text)
        self.assertTrue((await e._queue.get()).server_content.turn_complete);self.assertEqual(e._llm.calls,0)
        await e.close()
    async def test_open_without_target_asks_without_tools(self):
        e=engine();await e.send_client_content(turns={'parts':[{'text':'open'}]});await e._gen
        messages=[]
        while not e._queue.empty():messages.append(e._queue.get_nowait())
        self.assertTrue(any(m.server_content and m.server_content.output_transcription and 'What would' in m.server_content.output_transcription.text for m in messages))
        self.assertFalse(any(m.tool_call for m in messages));self.assertEqual(e._llm.calls,0);await e.close()
    async def test_busy_recognizer_drops_stale_incoming_audio(self):
        e=engine();e._stt=object();e._recognizing=True
        await e.send_realtime_input(audio={'data':b'\0'*3200})
        self.assertEqual(e._mic_bytes,0);await e.close()
    async def test_rapid_commands_wait_for_each_tool_result(self):
        e=engine()
        await e.send_client_content(turns={'parts':[{'text':'open youtube'}]})
        await e.send_client_content(turns={'parts':[{'text':'open notepad'}]})
        first=(await asyncio.wait_for(e._queue.get(),1)).tool_call.function_calls[0]
        self.assertEqual(first.name,'browser_control')
        await e.send_tool_response(function_responses=[SimpleNamespace(id=first.id,name=first.name,response={'result':'Opened YouTube'})])
        while True:
            message=await asyncio.wait_for(e._queue.get(),1)
            if message.tool_call:break
        second=message.tool_call.function_calls[0];self.assertEqual(second.name,'open_app')
        self.assertEqual(second.args['app_name'],'notepad');self.assertEqual(e._llm.calls,0);await e.close()
    async def test_interrupt_discards_queued_commands(self):
        e=engine();await e.send_client_content(turns={'parts':[{'text':'open youtube'}]})
        await e.send_client_content(turns={'parts':[{'text':'open notepad'}]})
        first=(await asyncio.wait_for(e._queue.get(),1)).tool_call.function_calls[0]
        e.interrupt();self.assertEqual(e._pending_inputs,[])
        await e.send_tool_response(function_responses=[SimpleNamespace(id=first.id,name=first.name,response={'result':'Opened YouTube'})])
        await e._gen
        while not e._queue.empty():self.assertFalse(e._queue.get_nowait().tool_call)
        await e.close()

if __name__=='__main__':unittest.main()
