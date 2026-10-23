"""Opt-in OpenAI Responses provider. Official HTTPS endpoint only."""
import json
from .base import Field,FunctionCall
from core.local_privacy import openai_access,validate_provider

DEFAULT_MODEL='gpt-6.1-sol'

class OpenAICloud:
    def __init__(self,cfg):
        validate_provider('openai_cloud',cfg)
        import httpx
        self._httpx=httpx;self.model=str(cfg.get('model') or DEFAULT_MODEL).strip()
        if not self.model or len(self.model)>120 or any(c.isspace() for c in self.model):raise ValueError('Enter a valid OpenAI model ID.')
        self.key=str(cfg['api_key']).strip();self.base='https://api.openai.com/v1';self.timeout=60
        self.caps={'tools':True,'tool_format':'openai','vision':False,'cloud_ai':True,'max_tools':None,'max_tool_chars':None}
        self._reasoning={}
    def _headers(self):return {'Authorization':'Bearer '+self.key,'Content-Type':'application/json'}
    def _body(self,messages,tools=None,stream=True):
        instructions=[];items=[];inserted=set()
        for message in messages:
            role=message.get('role');content=message.get('content')
            if role in ('system','developer'):
                if content:instructions.append(str(content))
            elif role=='tool':items.append({'type':'function_call_output','call_id':message['tool_call_id'],'output':str(content or '')})
            else:
                if content:items.append({'role':role,'content':content if isinstance(content,str) else str(content)})
                for tc in message.get('tool_calls',[]):
                    call_id=tc['id']
                    for reasoning in self._reasoning.get(call_id,[]):
                        if reasoning.get('id') not in inserted:items.append(reasoning);inserted.add(reasoning.get('id'))
                    fn=tc['function'];items.append({'type':'function_call','call_id':call_id,'name':fn['name'],'arguments':fn['arguments']})
        body={'model':self.model,'instructions':'\n'.join(instructions),'input':items,'store':False,'stream':stream,'max_output_tokens':4096}
        if self.model.startswith(('gpt-6','gpt-5','o3','o4')):
            body['reasoning']={'effort':'low'}
            body['include']=['reasoning.encrypted_content']
        if tools:
            body['tools']=[{'type':'function',**tool['function'],'strict':False} for tool in tools]
            body['parallel_tool_calls']=False
        return body
    def _error(self,status,text):
        code=''
        try:
            error=json.loads(text).get('error',{});message=error.get('message','');code=error.get('code') or error.get('type') or ''
        except (ValueError,AttributeError):message='Request failed.'
        message=str(message).replace(self.key,'[redacted]')[:250]
        if status==401:message='OpenAI rejected the API key. Update it in Settings > OpenAI connection.'
        elif status==429:
            if code in ('insufficient_quota','credit_balance_exhausted'):message='OpenAI API credits/quota are exhausted. Check API billing and add credits if needed. ChatGPT plan usage is separate.'
            elif code in ('project_spend_limit_exceeded','organization_spend_limit_exceeded','organization_usage_limit_exceeded'):message='OpenAI '+code.replace('_',' ')+'. Check the corresponding project or organization limit before retrying.'
            else:message='OpenAI rate limit reached. Wait before retrying. '+message
        if code:message+=' ['+str(code)+']'
        return RuntimeError(f'OpenAI {status}: '+message)
    def _output(self,output):
        text=[];calls=[];reasoning=[]
        for item in output:
            if item.get('type')=='reasoning':reasoning.append(item)
            elif item.get('type')=='message':
                for content in item.get('content',[]):
                    if content.get('type')=='output_text':text.append(content.get('text',''))
                    elif content.get('type')=='refusal':text.append(content.get('refusal',''))
            elif item.get('type')=='function_call':
                args=json.loads(item.get('arguments') or '{}')
                if not isinstance(args,dict):raise RuntimeError('OpenAI returned invalid function arguments.')
                call_id=item['call_id'];calls.append(FunctionCall(id=call_id,name=item['name'],args=args))
                self._reasoning[call_id]=list(reasoning)
        while len(self._reasoning)>128:self._reasoning.pop(next(iter(self._reasoning)))
        return ''.join(text),calls
    def complete(self,messages,tools=None,*,timeout=None,temperature=None):
        with openai_access(),self._httpx.Client(timeout=timeout or self.timeout,trust_env=False,follow_redirects=False) as client:
            response=client.post(self.base+'/responses',headers=self._headers(),json=self._body(messages,tools,False))
        if response.status_code>=400:raise self._error(response.status_code,response.text)
        data=response.json();text,calls=self._output(data.get('output',[]))
        if not text and not calls:raise RuntimeError('OpenAI returned no answer. '+str(data.get('incomplete_details') or data.get('error') or 'Please retry.'))
        return text,calls
    async def chat(self,messages,tools=None,*,stream=True,temperature=None):
        async with self._httpx.AsyncClient(timeout=self.timeout,trust_env=False,follow_redirects=False) as client:
            request=client.build_request('POST',self.base+'/responses',headers=self._headers(),json=self._body(messages,tools,stream))
            with openai_access():response=await client.send(request,stream=stream)
            try:
                if response.status_code>=400:
                    with openai_access():detail=(await response.aread()).decode('utf-8','replace')
                    raise self._error(response.status_code,detail)
                if not stream:
                    with openai_access():await response.aread()
                    text,calls=self._output(response.json().get('output',[]))
                    if text:yield {'text':text}
                    if calls:yield {'tool_calls':calls}
                    return
                iterator=response.aiter_lines().__aiter__();completed=None
                while True:
                    try:
                        with openai_access():line=await anext(iterator)
                    except StopAsyncIteration:break
                    if not line.startswith('data:'):continue
                    raw=line[5:].strip()
                    if raw=='[DONE]':break
                    event=json.loads(raw);kind=event.get('type')
                    if kind=='response.output_text.delta':yield {'text':event.get('delta','')}
                    elif kind=='response.refusal.delta':yield {'text':event.get('delta','')}
                    elif kind=='response.completed':completed=event['response']
                    elif kind in ('response.failed','response.incomplete','error'):raise RuntimeError('OpenAI could not finish the reply. Please retry; check API billing if this continues.')
                if completed is None:raise RuntimeError('OpenAI connection ended before the reply finished. Please retry.')
                _,calls=self._output(completed.get('output',[]))
                if calls:yield {'tool_calls':calls}
            finally:
                with openai_access():await response.aclose()
    def probe(self):
        text,_=self.complete([{'role':'user','content':'Reply with: JARVIS connected.'}],timeout=25)
        return True,text
    def ensure_vision_known(self,*args):return False

PROVIDER={'id':'openai_cloud','kind':'llm','label':'OpenAI cloud','hint':'OpenAI Responses API; requires your own API key',
 'requires':('httpx',),'catalog':({'id':'openai_cloud','label':'OpenAI cloud','local':False,'values':{'model':DEFAULT_MODEL}},),
 'needs':(Field('model','Model',default=DEFAULT_MODEL),Field('api_key','API key',kind='secret'),Field('cloud_enabled','Allow OpenAI requests',kind='bool',default=False)),
 'caps':{'tools':True,'tool_format':'openai','vision':False},'factory':OpenAICloud}
def available():return True
