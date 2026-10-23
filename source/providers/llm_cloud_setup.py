"""Disconnected state only. No model, network request, download or fallback."""
class CloudSetup:
    caps={'tools':True,'tool_format':'openai','vision':False,'cloud_ai':False,'max_tools':None,'max_tool_chars':None}
    def complete(self,*args,**kwargs):
        raise RuntimeError('AI is not connected. Open Settings > AI connection and connect Gemini or OpenAI. No offline AI is installed.')
    async def chat(self,*args,**kwargs):
        self.complete()
        if False:yield {}
    def ensure_vision_known(self,*args):return False
PROVIDER={'id':'cloud_setup','kind':'llm','label':'Connect cloud AI','hint':'No offline AI model is installed',
 'requires':(),'needs':(),'caps':CloudSetup.caps,'factory':lambda cfg:CloudSetup()}
def available():return True
