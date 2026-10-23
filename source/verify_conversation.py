"""Production voice pipeline with real local STT/TTS and mocked Gemini HTTP."""
import asyncio,json,os,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx

def main():
    with tempfile.TemporaryDirectory() as folder:
        previous=os.environ.get('JARVIS_DATA_DIR');os.environ['JARVIS_DATA_DIR']=str(Path(folder)/'data')
        os.environ['JARVIS_OFFSCREEN_STATIC']='1'
        from core.local_privacy import default_config
        cfg=Path(folder)/'settings.json';cfg.write_text(json.dumps(default_config()))
        from memory import config_manager,local_database
        import ui
        from main import JarvisLive
        async def check():
            from providers import audio
            from providers.llm_gemini_cloud import GeminiCloud
            original_init=GeminiCloud.__init__;requests=[]
            def handler(request):
                body=json.loads(request.content);requests.append(body)
                text=body['contents'][-1]['parts'][0].get('text','').lower()
                answer='Two plus two is four.' if 'two' in text or '2 plus 2' in text else 'Plants use sunlight to turn water and carbon dioxide into sugar and oxygen.'
                chunk={'candidates':[{'content':{'parts':[{'text':answer}]},'finishReason':'STOP'}]}
                return httpx.Response(200,text='data: '+json.dumps(chunk)+'\n\n')
            transport=httpx.MockTransport(handler)
            def init(llm,cfg):
                original_init(llm,cfg)
                llm._httpx=SimpleNamespace(AsyncClient=lambda **kw:httpx.AsyncClient(transport=transport,**kw))
            patches=[patch('core.cloud_config.load',return_value={'enabled':True,'provider':'gemini_cloud','api_key':'SYNTHETIC-TEST-KEY','model':'gemini-3.5-flash-lite'}),patch.object(GeminiCloud,'__init__',init)]
            for item in patches:item.start()
            native=ui.JarvisUI('face.png');owner=JarvisLive(native);reports=[]
            try:
                owner._engine_caps=owner._resolve_engine_caps();config=owner._build_config()
                async with owner._open_session('cloud-test',config) as engine:
                    assert engine.store.path.is_relative_to(Path(folder))
                    for command in ['Hello Jarvis.','What is two plus two?','Explain photosynthesis in one sentence.','Open YouTube.','System diagnostics.']:
                        wave=await asyncio.to_thread(engine._tts._synth_blocking,command)
                        engine._mic=[audio.wav_to_pcm(wave,16000)]
                        heard=await engine.flush_microphone();reply=[];pcm_bytes=0;tool=None
                        while True:
                            msg=await asyncio.wait_for(engine._queue.get(),120)
                            if msg.data:pcm_bytes+=len(msg.data)
                            if msg.tool_call:
                                call=msg.tool_call.function_calls[0];tool=call.name
                                assert call.name=='browser_control' and 'youtube.com' in call.args['url']
                                await engine.send_tool_response(function_responses=[SimpleNamespace(id=call.id,name=call.name,response={'result':'status=done action=browser_control'})])
                            if msg.server_content:
                                if msg.server_content.output_transcription:reply.append(msg.server_content.output_transcription.text)
                                if msg.server_content.turn_complete:break
                        answer=' '.join(reply)
                        assert answer.strip().casefold()!=heard.strip().casefold() and pcm_bytes>0,(heard,answer)
                        reports.append({'input':command,'recognized':heard,'answer':answer,'reply_pcm_bytes':pcm_bytes,'tool':tool})
                        native._app.processEvents()
                    assert any(v in reports[1]['answer'].casefold() for v in ('4','four')),reports[1]
                    assert any(v in reports[2]['answer'].casefold() for v in ('plant','light','sun')),reports[2]
                    assert reports[3]['tool']=='browser_control'
                    assert 'RAM:' in reports[4]['answer']
                    assert engine.store.stats()['messages']>=10
                    await engine.close()
                root=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent
                assert len(requests)==2,len(requests)
                (root/'conversation-diagnostics.json').write_text(json.dumps({'production_session_factory':'passed','native_speech_whisper_windows_tts':'passed','gemini_http':'mocked; no live key used','different_requests_have_different_answers':'passed','turns':reports,'physical_microphone_speaker_and_browser':'not accessed'},indent=2),encoding='utf-8')
                print(json.dumps(reports))
            finally:
                native._win.close();native._app.processEvents()
                for item in reversed(patches):item.stop()
        try:
            with patch.object(config_manager,'CONFIG_FILE',cfg),patch.object(ui,'API_FILE',cfg):
                asyncio.run(check())
        finally:
            if previous is None:os.environ.pop('JARVIS_DATA_DIR',None)
            else:os.environ['JARVIS_DATA_DIR']=previous

if __name__=='__main__':main()
