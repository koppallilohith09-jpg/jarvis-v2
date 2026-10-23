import asyncio,json,os,socket,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from core import local_privacy as policy,cloud_config
from providers.llm_openai_cloud import OpenAICloud
from providers.llm_gemini_cloud import GeminiCloud

KEY='SYNTHETIC-OPENAI-KEY-NOT-REAL'
def provider():return OpenAICloud({'cloud_enabled':True,'api_key':KEY})
def stream(events):return ''.join('data: '+json.dumps(e)+'\n\n' for e in events)

class Cloud(unittest.IsolatedAsyncioTestCase):
    def test_access_is_request_scoped_and_does_not_enable_other_hosts(self):
        with self.assertRaises(ValueError):OpenAICloud({'api_key':KEY})
        with policy.openai_access():
            policy.audit_network('socket.getaddrinfo',('api.openai.com',443))
            policy.audit_network('socket.getaddrinfo',(b'api.openai.com',443))
            with self.assertRaises(PermissionError):policy.audit_network('socket.connect',(None,('1.2.3.4',443)))
            resolved=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('1.2.3.4',443))]
            with patch('socket.getaddrinfo',return_value=resolved):policy._resolve_in_context('api.openai.com',443)
            policy.audit_network('socket.connect',(None,('1.2.3.4',443)))
            with self.assertRaises(PermissionError):policy.audit_network('socket.connect',(None,('1.2.3.5',443)))
            with self.assertRaises(PermissionError):policy.audit_network('socket.getaddrinfo',('example.com',443))
            with self.assertRaises(PermissionError):policy.audit_network('socket.connect',(None,('1.2.3.4',80)))
        with self.assertRaises(PermissionError):policy.audit_network('socket.connect',(None,('1.2.3.4',443)))
    async def test_responses_stream_and_reasoning_follow_function_output(self):
        llm=provider();requests=[]
        reasoning={'type':'reasoning','id':'r1','summary':[],'encrypted_content':'synthetic-encrypted-context'}
        call={'type':'function_call','call_id':'call_1','name':'open_app','arguments':'{"app_name":"notepad"}'}
        def handler(request):
            body=json.loads(request.content);requests.append(body)
            self.assertEqual(str(request.url),'https://api.openai.com/v1/responses')
            if len(requests)==1:
                return httpx.Response(200,text=stream([{'type':'response.completed','response':{'output':[reasoning,call]}}]))
            self.assertIn(reasoning,body['input'])
            self.assertIn({'type':'function_call_output','call_id':'call_1','output':'status=done'},body['input'])
            return httpx.Response(200,text=stream([{'type':'response.output_text.delta','delta':'Notepad is open.'},{'type':'response.completed','response':{'output':[{'type':'message','content':[{'type':'output_text','text':'Notepad is open.'}]}]}}]))
        transport=httpx.MockTransport(handler)
        llm._httpx=SimpleNamespace(AsyncClient=lambda **kw:httpx.AsyncClient(transport=transport,**kw))
        first=[event async for event in llm.chat([{'role':'user','content':'Open the notes program.'}],[{'type':'function','function':{'name':'open_app','parameters':{'type':'object','properties':{}}}}])]
        self.assertEqual(first[0]['tool_calls'][0].args,{'app_name':'notepad'})
        history=[{'role':'user','content':'Open the notes program.'},{'role':'assistant','content':None,'tool_calls':[{'id':'call_1','type':'function','function':{'name':'open_app','arguments':call['arguments']}}]},{'role':'tool','tool_call_id':'call_1','content':'status=done'}]
        second=[e async for e in llm.chat(history)]
        self.assertEqual(second,[{'text':'Notepad is open.'}]);self.assertFalse(requests[0]['store'])
        self.assertEqual(requests[0]['tools'][0]['type'],'function')
        self.assertIn('reasoning.encrypted_content',requests[0]['include'])
    async def test_failed_and_truncated_cloud_responses_are_visible_errors(self):
        llm=provider()
        for status,text in [(401,json.dumps({'error':{'message':KEY}})),(429,'{}'),(200,stream([{'type':'response.output_text.delta','delta':'partial'}]))]:
            transport=httpx.MockTransport(lambda req:httpx.Response(status,text=text))
            llm._httpx=SimpleNamespace(AsyncClient=lambda **kw:httpx.AsyncClient(transport=transport,**kw))
            with self.assertRaises(RuntimeError) as error:[e async for e in llm.chat([{'role':'user','content':'Hello'}])]
            self.assertNotIn(KEY,str(error.exception))
    def test_credit_and_rate_limits_have_different_recovery_instructions(self):
        llm=provider()
        quota=str(llm._error(429,json.dumps({'error':{'code':'insufficient_quota'}})))
        rate=str(llm._error(429,json.dumps({'error':{'code':'rate_limit_exceeded'}})))
        self.assertIn('API billing',quota);self.assertIn('Wait',rate);self.assertNotIn('add credits',rate)

class ConnectionUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ['QT_QPA_PLATFORM']='offscreen'
        from PyQt6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication(['cloud-test'])
    def test_key_masked_protected_and_connection_changes_pipeline(self):
        from core.openai_setup import ConnectionDialog
        from PyQt6.QtWidgets import QLineEdit
        from memory.config_manager import get_pipeline,get_provider_config
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'JARVIS_DATA_DIR':str(Path(folder)/'data')}):
            dialog=ConnectionDialog();dialog.provider.setCurrentIndex(dialog.provider.findData('openai_cloud'));dialog.key.setText(KEY)
            self.assertEqual(dialog.key.echoMode(),QLineEdit.EchoMode.Password)
            with patch.object(OpenAICloud,'probe',return_value=(True,'JARVIS connected.')):
                dialog.connect_button.click();deadline=time.monotonic()+3
                while not cloud_config.active() and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
            self.assertTrue(cloud_config.active());self.assertNotIn(KEY,cloud_config.path().read_text())
            self.assertEqual(get_pipeline()['llm'],'openai_cloud');self.assertEqual(get_provider_config('openai_cloud')['api_key'],KEY)
            dialog.disconnect();self.assertFalse(cloud_config.active());dialog.close()

    def test_gemini_requires_data_notice_and_changes_provider_only_after_success(self):
        from core.openai_setup import ConnectionDialog
        from memory.config_manager import get_pipeline
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'JARVIS_DATA_DIR':str(Path(folder)/'data')}):
            dialog=ConnectionDialog();dialog.key.setText(KEY)
            self.assertEqual(dialog.provider.currentData(),'gemini_cloud')
            dialog.connect_button.click();self.assertFalse(cloud_config.active());self.assertIn('accept',dialog.status.text())
            dialog.google_consent.setChecked(True)
            with patch.object(GeminiCloud,'probe',return_value=(True,'JARVIS connected.')):
                dialog.connect_button.click();deadline=time.monotonic()+3
                while not cloud_config.active() and time.monotonic()<deadline:self.app.processEvents();time.sleep(.01)
            self.assertEqual(get_pipeline()['llm'],'gemini_cloud');self.assertNotIn(KEY,cloud_config.path().read_text())
            dialog.disconnect();self.assertEqual(get_pipeline()['llm'],'cloud_setup');dialog.close()

class Gemini(unittest.IsolatedAsyncioTestCase):
    async def test_dns_worker_retains_only_the_callers_provider_scope(self):
        def resolve(host,port,*args,**kwargs):
            policy.audit_network('socket.getaddrinfo',(host,port))
            return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('192.0.2.10',443))]
        loop=asyncio.get_running_loop()
        with patch('socket.getaddrinfo',side_effect=resolve):
            with policy.gemini_access():
                self.assertTrue(await loop.getaddrinfo('generativelanguage.googleapis.com',443))
                with self.assertRaises(PermissionError):await loop.getaddrinfo('api.openai.com',443)
            with policy.openai_access():
                self.assertTrue(await loop.getaddrinfo('api.openai.com',443))
                with self.assertRaises(PermissionError):await loop.getaddrinfo('example.com',443)
            with self.assertRaises(PermissionError):await loop.getaddrinfo('generativelanguage.googleapis.com',443)

    async def test_provider_scopes_are_isolated_between_concurrent_tasks(self):
        addresses={'generativelanguage.googleapis.com':'192.0.2.10','api.openai.com':'192.0.2.20'}
        def resolve(host,port,*args,**kwargs):
            policy.audit_network('socket.getaddrinfo',(host,port))
            return [(socket.AF_INET,socket.SOCK_STREAM,6,'',(addresses[host],443))]
        ready=asyncio.Event()
        async def scoped(scope,host,other):
            with scope():
                ready.set();await asyncio.sleep(0)
                await asyncio.get_running_loop().getaddrinfo(host,443)
                policy.audit_network('socket.connect',(None,(addresses[host],443)))
                with self.assertRaises(PermissionError):policy.audit_network('socket.connect',(None,(addresses[other],443)))
                with self.assertRaises(PermissionError):await asyncio.get_running_loop().getaddrinfo(other,443)
        async def unrelated():
            await ready.wait()
            with self.assertRaises(PermissionError):await asyncio.get_running_loop().getaddrinfo('generativelanguage.googleapis.com',443)
        with patch('socket.getaddrinfo',side_effect=resolve):
            await asyncio.gather(unrelated(),scoped(policy.gemini_access,'generativelanguage.googleapis.com','api.openai.com'),scoped(policy.openai_access,'api.openai.com','generativelanguage.googleapis.com'))

    async def test_child_task_cannot_reuse_scope_after_request_finishes(self):
        ready=asyncio.Event()
        def resolve(host,port,*args,**kwargs):
            policy.audit_network('socket.getaddrinfo',(host,port))
            return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('192.0.2.10',443))]
        async def late_request():
            await ready.wait()
            with self.assertRaises(PermissionError):await asyncio.get_running_loop().getaddrinfo('generativelanguage.googleapis.com',443)
            with self.assertRaises(PermissionError):policy.audit_network('socket.connect',(None,('192.0.2.10',443)))
        with patch('socket.getaddrinfo',side_effect=resolve):
            with policy.gemini_access():
                await asyncio.get_running_loop().getaddrinfo('generativelanguage.googleapis.com',443)
                pending=asyncio.create_task(late_request())
            ready.set();await pending

    def test_google_scope_does_not_allow_openai_or_other_hosts(self):
        with policy.gemini_access():
            policy.audit_network('socket.getaddrinfo',('generativelanguage.googleapis.com',443))
            for host in ('api.openai.com','example.com'):
                with self.assertRaises(PermissionError):policy.audit_network('socket.getaddrinfo',(host,443))
        with self.assertRaises(PermissionError):policy.audit_network('socket.getaddrinfo',('generativelanguage.googleapis.com',443))

    async def test_native_stream_tools_keep_signatures_and_function_responses(self):
        llm=GeminiCloud({'cloud_enabled':True,'api_key':KEY});requests=[]
        def handler(request):
            self.assertEqual(request.url.path,'/v1beta/models/'+llm.model+':streamGenerateContent')
            self.assertEqual(request.headers['x-goog-api-key'],KEY)
            self.assertNotIn(KEY,str(request.url));body=json.loads(request.content);requests.append(body)
            self.assertEqual(body['generationConfig']['thinkingConfig']['thinkingLevel'],'LOW')
            if len(requests)==1:
                self.assertIn('functionDeclarations',body['tools'][0])
                parts=[{'functionCall':{'id':'g1','name':'open_app','args':{'app_name':'notepad'}},'thoughtSignature':'synthetic'}]
            else:
                self.assertEqual(body['contents'][1]['parts'][0]['thoughtSignature'],'synthetic')
                self.assertEqual(body['contents'][2]['parts'][0]['functionResponse']['name'],'open_app')
                parts=[{'text':'Notepad is open.'}]
            return httpx.Response(200,text=stream([{'candidates':[{'content':{'parts':parts},'finishReason':'STOP'}]}]))
        transport=httpx.MockTransport(handler);llm._httpx=SimpleNamespace(AsyncClient=lambda **kw:httpx.AsyncClient(transport=transport,**kw))
        tools=[{'type':'function','function':{'name':'open_app','parameters':{'type':'object','properties':{}}}}]
        first=[e async for e in llm.chat([{'role':'user','content':'Open Notepad'}],tools)]
        self.assertEqual(first[0]['tool_calls'][0].args,{'app_name':'notepad'})
        history=[{'role':'user','content':'Open Notepad'},{'role':'assistant','content':None,'tool_calls':[{'id':'g1','type':'function','function':{'name':'open_app','arguments':'{"app_name":"notepad"}'}}]},{'role':'tool','tool_call_id':'g1','content':'status=done'}]
        self.assertEqual([e async for e in llm.chat(history)],[{'text':'Notepad is open.'}])
        self.assertNotIn(KEY,str(llm._error(500,json.dumps({'error':{'message':KEY}}))))
        self.assertIn('Check available Gemini models',str(llm._error(404,'{}')))

    def test_probe_only_lists_models_without_generating_or_putting_key_in_url(self):
        llm=GeminiCloud({'cloud_enabled':True,'api_key':KEY});requests=[]
        def handler(request):
            requests.append(request);self.assertEqual(request.method,'GET')
            self.assertEqual(request.url.path,'/v1beta/models');self.assertNotIn(KEY,str(request.url))
            return httpx.Response(200,json={'models':[{'name':'models/'+llm.model,'supportedGenerationMethods':['generateContent']},{'name':'models/gemini-speech','supportedGenerationMethods':['bidiGenerateContent']}]})
        transport=httpx.MockTransport(handler);llm._httpx=SimpleNamespace(Client=lambda **kw:httpx.Client(transport=transport,**kw))
        ok,message=llm.probe();self.assertTrue(ok);self.assertIn('No reply was generated',message);self.assertEqual(len(requests),1)

    def test_timeout_is_distinct_from_invalid_key(self):
        llm=GeminiCloud({'cloud_enabled':True,'api_key':KEY})
        def handler(request):raise httpx.ReadTimeout('synthetic timeout',request=request)
        transport=httpx.MockTransport(handler);llm._httpx=SimpleNamespace(Client=lambda **kw:httpx.Client(transport=transport,**kw))
        with self.assertRaisesRegex(RuntimeError,'key has not been marked invalid'):llm.probe()

    async def test_partial_stream_and_quota_are_visible_errors(self):
        llm=GeminiCloud({'cloud_enabled':True,'api_key':KEY})
        for status,body in [(429,'{}'),(200,stream([{'candidates':[{'content':{'parts':[{'text':'partial'}]}}]}]))]:
            transport=httpx.MockTransport(lambda req:httpx.Response(status,text=body))
            llm._httpx=SimpleNamespace(AsyncClient=lambda **kw:httpx.AsyncClient(transport=transport,**kw))
            with self.assertRaises(RuntimeError):[event async for event in llm.chat([{'role':'user','content':'Explain gravity'}])]
        self.assertIn('No paid model or offline AI',str(llm._error(429,'{}')))

if __name__=='__main__':unittest.main()
