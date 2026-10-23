import asyncio,unittest
from providers.engine_pipeline import PipelineEngine
from core.local_conversation import greeting,input_echo

class Conversation(unittest.IsolatedAsyncioTestCase):
    async def test_greeting_is_an_answer_without_model_or_repeating_user(self):
        class NoModel:
            caps={}
            async def chat(self,*args):raise AssertionError('Greeting must be immediate.')
        engine=PipelineEngine(NoModel())
        await engine.send_client_content(turns={'parts':[{'text':'hello jarvis'}]});await engine._gen
        self.assertNotEqual(engine._history[-1]['content'].casefold(),'hello jarvis')
        self.assertIn('help',engine._history[-1]['content']);await engine.close()
    async def test_repeated_input_is_never_sent_to_speech_and_retry_answers(self):
        class EchoThenAnswer:
            caps={}
            calls=0
            async def chat(self,*args):
                self.calls+=1
                yield {'text':'What is two plus two?' if self.calls==1 else 'Two plus two is four.'}
        class Voice:
            spoken=[]
            async def speak(self,text):
                self.spoken.append(text)
                if False:yield b''
        llm=EchoThenAnswer();voice=Voice();engine=PipelineEngine(llm,tts=voice)
        await engine.send_client_content(turns={'parts':[{'text':'What is two plus two?'}]});await engine._gen
        self.assertEqual(llm.calls,2);self.assertEqual(voice.spoken,['Two plus two is four.']);await engine.close()
    def test_greeting_does_not_swallow_commands_and_requested_repeat_is_allowed(self):
        self.assertIsNone(greeting('hello jarvis open youtube'))
        self.assertTrue(input_echo('What is two plus two?','what is two plus two'))
        self.assertFalse(input_echo('Repeat hello','Repeat hello'))
    async def test_stop_ends_interrupted_turn_and_next_request_can_answer(self):
        class Slow:
            caps={}
            async def chat(self,*args):
                await asyncio.sleep(30)
                yield {'text':'Late reply.'}
        engine=PipelineEngine(Slow())
        await engine.send_client_content(turns={'parts':[{'text':'Explain gravity.'}]})
        await asyncio.sleep(0);engine.interrupt()
        self.assertTrue((await engine._queue.get()).server_content.turn_complete)
        await engine.send_client_content(turns={'parts':[{'text':'Hello Jarvis.'}]});await engine._gen
        self.assertIn('help',engine._history[-1]['content']);await engine.close()

if __name__=='__main__':unittest.main()
