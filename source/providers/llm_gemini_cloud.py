"""Native Gemini REST/SSE, cloud only; keys stay in request headers."""
import copy,json,re,uuid
from httpx import Timeout,TimeoutException
from .base import Field,FunctionCall
from core.local_privacy import gemini_access,validate_provider
DEFAULT_MODEL='gemini-3.5-flash-lite'
class GeminiCloud:
    def __init__(self,cfg):
        validate_provider('gemini_cloud',cfg)
        import httpx
        self._httpx=httpx;self.key=str(cfg['api_key']).strip()
        self.model=str(cfg.get('model') or DEFAULT_MODEL).strip().removeprefix('models/')
        if not re.fullmatch(r'gemini-[A-Za-z0-9_.-]+',self.model):raise ValueError('Use a Gemini model ID, such as '+DEFAULT_MODEL)
        self.base='https://generativelanguage.googleapis.com/v1beta';self.timeout=60;self._contexts={}
        self.caps={'tools':True,'tool_format':'openai','vision':False,'cloud_ai':True,'cloud_label':'Gemini','max_tools':None,'max_tool_chars':None}
    def _headers(self):return {'x-goog-api-key':self.key,'Content-Type':'application/json'}
    def _body(self,messages,tools=None,stream=True):
        contents=[];instructions=[];names={}
        for message in messages:
            role=message.get('role');text=message.get('content');parts=[]
            if role in ('system','developer'):
                if text:instructions.append(str(text))
                continue
            target='model' if role=='assistant' else 'user'
            if role=='tool':
                name=message.get('name') or names.get(message.get('tool_call_id'))
                if not name:raise ValueError('Function response is missing its function name.')
                parts=[{'functionResponse':{'name':name,'response':{'result':str(text or '')}}}]
            else:
                if text:parts.append({'text':str(text)})
                for call in message.get('tool_calls',[]):
                    fn=call['function'];names[call['id']]=fn['name']
                    part=self._contexts.get(call['id']) or {'functionCall':{'name':fn['name'],'args':json.loads(fn['arguments'] or '{}')}}
                    parts.append(copy.deepcopy(part))
            if parts:
                if contents and contents[-1]['role']==target:contents[-1]['parts'].extend(parts)
                else:contents.append({'role':target,'parts':parts})
        body={'contents':contents,'generationConfig':{'maxOutputTokens':4096}}
        if instructions:body['systemInstruction']={'parts':[{'text':'\n'.join(instructions)}]}
        if self.model.startswith('gemini-3'):body['generationConfig']['thinkingConfig']={'thinkingLevel':'LOW'}
        if tools:body['tools']=[{'functionDeclarations':[{'name':t['function']['name'],'description':t['function'].get('description',''),'parametersJsonSchema':t['function'].get('parameters',{'type':'object','properties':{}})} for t in tools]}]
        return body
    def _error(self,status,text):
        try:message=str(json.loads(text).get('error',{}).get('message','Request failed.'))
        except (ValueError,AttributeError):message='Request failed.'
        message=message.replace(self.key,'[redacted]')[:220]
        if status in (401,403):message='Check your Google AI Studio key and project permissions. '+message
        elif status==404:message='Model unavailable for this key/project. Check available Gemini models, choose one listed, then retry. '+message
        elif status==429:message='Gemini quota/rate limit reached. Wait for your free quota to reset. No paid model or offline AI will be selected automatically.'
        return RuntimeError(f'Gemini {status}: '+message)
    def _output(self,data):
        if data.get('error'):raise self._error(400,json.dumps(data))
        texts=[];calls=[];finish=None
        for candidate in data.get('candidates',[]):
            finish=candidate.get('finishReason') or finish
            for part in candidate.get('content',{}).get('parts',[]):
                if part.get('thought'):continue
                if part.get('text'):texts.append(part['text'])
                if part.get('functionCall'):
                    fn=part['functionCall'];args=fn.get('args') or {}
                    if not isinstance(args,dict):raise RuntimeError('Gemini returned invalid function arguments.')
                    call_id=fn.get('id') or 'gemini_'+uuid.uuid4().hex;self._contexts[call_id]=copy.deepcopy(part)
                    calls.append(FunctionCall(id=call_id,name=fn['name'],args=args))
        while len(self._contexts)>128:self._contexts.pop(next(iter(self._contexts)))
        if finish and finish!='STOP':raise RuntimeError('Gemini reply stopped: '+str(finish))
        if data.get('promptFeedback',{}).get('blockReason'):raise RuntimeError('Gemini did not accept this request: '+data['promptFeedback']['blockReason'])
        return ''.join(texts),calls,finish
    def complete(self,messages,tools=None,*,timeout=None,temperature=None):
        try:
            with gemini_access(),self._httpx.Client(timeout=Timeout(timeout or self.timeout,connect=8),trust_env=False,follow_redirects=False) as client:
                response=client.post(self.base+'/models/'+self.model+':generateContent',headers=self._headers(),json=self._body(messages,tools,False))
        except TimeoutException:raise RuntimeError('Google timed out while answering. Check your connection and retry; the key has not been marked invalid.') from None
        if response.status_code>=400:raise self._error(response.status_code,response.text)
        text,calls,_=self._output(response.json())
        if not text and not calls:raise RuntimeError('Gemini returned no answer. Please retry.')
        return text,calls
    async def chat(self,messages,tools=None,*,stream=True,temperature=None):
        try:
            async with self._httpx.AsyncClient(timeout=Timeout(self.timeout,connect=8),trust_env=False,follow_redirects=False) as client:
                suffix=':streamGenerateContent?alt=sse' if stream else ':generateContent'
                request=client.build_request('POST',self.base+'/models/'+self.model+suffix,headers=self._headers(),json=self._body(messages,tools,stream))
                with gemini_access():response=await client.send(request,stream=stream)
                try:
                    if response.status_code>=400:
                        with gemini_access():detail=(await response.aread()).decode('utf-8','replace')
                        raise self._error(response.status_code,detail)
                    if not stream:
                        with gemini_access():await response.aread()
                        text,calls,_=self._output(response.json())
                        if text:yield {'text':text}
                        if calls:yield {'tool_calls':calls}
                        if not text and not calls:raise RuntimeError('Gemini returned no answer.')
                        return
                    finished=False;visible=False;iterator=response.aiter_lines().__aiter__()
                    while True:
                        try:
                            with gemini_access():line=await anext(iterator)
                        except StopAsyncIteration:break
                        if not line.startswith('data:'):continue
                        text,calls,finish=self._output(json.loads(line[5:].strip()))
                        if text:visible=True;yield {'text':text}
                        if calls:visible=True;yield {'tool_calls':calls}
                        if finish=='STOP':finished=True
                    if not finished:raise RuntimeError('Gemini connection ended before the reply finished. Please retry.')
                    if not visible:raise RuntimeError('Gemini returned no answer.')
                finally:
                    with gemini_access():await response.aclose()
        except TimeoutException:raise RuntimeError('Google timed out while answering. Check your connection and retry; no offline AI is installed.') from None
    def list_models(self):
        try:
            with gemini_access(),self._httpx.Client(timeout=Timeout(20,connect=8),trust_env=False,follow_redirects=False) as client:
                response=client.get(self.base+'/models',params={'pageSize':1000},headers=self._headers())
        except TimeoutException:raise RuntimeError('Google did not respond to the key/model check. Check your connection and retry. No reply generation was requested; the key has not been marked invalid.') from None
        if response.status_code>=400:raise self._error(response.status_code,response.text)
        return sorted({item.get('name','').removeprefix('models/') for item in response.json().get('models',[]) if item.get('name','').startswith('models/gemini-') and 'generateContent' in item.get('supportedGenerationMethods',[])})
    def probe(self):
        if self.model not in self.list_models():raise self._error(404,'{}')
        return True,'Key accepted and model listed. No reply was generated by this check. Chat still depends on available quota and your connection.'
    def ensure_vision_known(self,*args):return False
PROVIDER={'id':'gemini_cloud','kind':'llm','label':'Google Gemini','hint':'Native Gemini API; free-tier quotas apply','requires':('httpx',),'catalog':({'id':'gemini_cloud','label':'Google Gemini','local':False,'values':{'model':DEFAULT_MODEL}},),'needs':(Field('model','Model',default=DEFAULT_MODEL),),'caps':{'tools':True,'tool_format':'openai','vision':False},'factory':GeminiCloud}
def available():return True
