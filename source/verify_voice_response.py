"""Synthetic offline speech -> recognition -> command -> spoken response bytes."""
import asyncio,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace

async def speech_check():
    from providers.tts_system import SystemTTS
    from providers.stt_whisper import WhisperSTT
    from providers.engine_pipeline import PipelineEngine
    from providers import audio
    class NoModel:
        caps={'tools':True,'tool_format':'openai'}
        async def chat(self,*args):
            raise AssertionError('Explicit spoken YouTube command must skip model inference.')
            yield {}
    tts=SystemTTS({'voice':'Microsoft David Desktop'});stt=WhisperSTT({})
    pcm=audio.wav_to_pcm(await asyncio.to_thread(tts._synth_blocking,'Open YouTube.'),16000)
    cfg=SimpleNamespace(system_instruction='',tools=[{'function_declarations':[{'name':'browser_control','description':'Open website','parameters':{'type':'OBJECT','properties':{}}}]}])
    engine=PipelineEngine(NoModel(),stt,tts,config=cfg)
    engine._mic=[pcm]
    heard=await engine.flush_microphone();assert 'youtube' in heard.casefold().replace(' ',''),heard
    call=None
    while call is None:
        msg=await asyncio.wait_for(engine._queue.get(),15)
        if msg.tool_call:call=msg.tool_call.function_calls[0]
    assert call.name=='browser_control' and call.args['url']=='https://www.youtube.com'
    # A deliberately malformed tool status reproduces the former receiver crash.
    await engine.send_tool_response(function_responses=[SimpleNamespace(id=call.id,name=call.name,response={'result':'status=unverified action=browser_control reason="test browser confirmation unavailable'})])
    await asyncio.wait_for(engine._gen,90)
    reply=[];pcm_bytes=0;ended=False
    while not engine._queue.empty():
        msg=engine._queue.get_nowait()
        if msg.data:pcm_bytes+=len(msg.data)
        if msg.server_content:
            if msg.server_content.output_transcription:reply.append(msg.server_content.output_transcription.text)
            ended|=bool(msg.server_content.turn_complete)
    assert ended and pcm_bytes>0 and 'could not confirm' in ' '.join(reply),reply
    engine._mic=[audio.wav_to_pcm(await asyncio.to_thread(tts._synth_blocking,'Hello Jarvis.'),16000)]
    greeting_heard=await engine.flush_microphone();await asyncio.wait_for(engine._gen,60)
    answer=engine._history[-1]['content']
    assert 'help' in answer.lower() and answer.casefold().strip('.!?')!=greeting_heard.casefold().strip('.!?'),answer
    await engine.close()
    return {'speech_engine':'Mark-LVI SystemTTS / Windows System.Speech','synthetic_speech_recognized':heard,'direct_website_command':'passed (no browser launched)','malformed_tool_status_survives':'passed','spoken_response_pcm_bytes':pcm_bytes,'hello_jarvis_recognized':greeting_heard,'greeting_answer':answer,'microphone_and_speaker_hardware':'not accessed'}

def main():
    from test_voice_response import VoiceReceiver,VoiceUI
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(cls) for cls in (VoiceReceiver,VoiceUI)])
    result=unittest.TextTestRunner().run(suite)
    if not result.wasSuccessful():raise AssertionError('Voice receiver/UI checks failed.')
    report=asyncio.run(speech_check());report['progressive_chat_and_hold_button']='passed'
    root=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent
    (root/'voice-response-diagnostics.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))

if __name__=='__main__':main()
