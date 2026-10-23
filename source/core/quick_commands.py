"""Small, explicit launch intents. Ambiguous speech never becomes keystrokes."""
import re
from urllib.parse import urlparse

SITES={'youtube':'https://www.youtube.com','you tube':'https://www.youtube.com','google':'https://www.google.com','gmail':'https://mail.google.com','wikipedia':'https://www.wikipedia.org','github':'https://github.com','reddit':'https://www.reddit.com','instagram':'https://www.instagram.com','facebook':'https://www.facebook.com','whatsapp web':'https://web.whatsapp.com','chatgpt':'https://chatgpt.com'}

def parse(text):
    if not isinstance(text,str):return None
    text=re.sub(r'^(?:hey\s+)?jarvis[,\s:]+','',text.strip(),flags=re.I)
    text=re.sub(r'^(?:(?:can|could|would) you\s+)?(?:please\s+)?','',text,flags=re.I).strip().rstrip('.!?')
    match=re.fullmatch(r'(?:open|launch|start|go to)\b\s*(.*?)\s*(?:please)?',text,flags=re.I)
    if not match:return None
    target=match.group(1).strip()
    if not target or target.lower() in ('it','that','this','something','the app','the website'):
        return {'reply':'What would you like me to open? Say, for example, open YouTube or open Notepad.'}
    if re.search(r'\b(?:and|then|after|with|using)\b|[;&|<>\n]',target,re.I):return None
    key=target.lower().removeprefix('the ').strip()
    if key in SITES:return {'name':'browser_control','args':{'action':'go_to','url':SITES[key]},'label':target}
    if re.fullmatch(r'(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?',target,re.I):
        url=target if '://' in target else 'https://'+target
        if urlparse(url).scheme in ('http','https'):return {'name':'browser_control','args':{'action':'go_to','url':url},'label':target}
    if re.fullmatch(r'[\w +().-]{1,70}',target):return {'name':'open_app','args':{'app_name':target},'label':target}
    return None

def result_line(plan,payload):
    import json
    if isinstance(payload,str) and payload.startswith('status='):
        import shlex
        payload=payload.partition(' -- ')[0]
        try:fields=dict(part.split('=',1) for part in shlex.split(payload) if '=' in part)
        except ValueError:
            # Tool output is data, not shell syntax. Truncation or an apostrophe
            # in an unquoted app name must never crash the receive loop.
            fields={m.group(1):m.group(2).strip().strip('"') for m in re.finditer(r'(\w+)=(.*?)(?=\s+\w+=|$)',payload)}
        if fields.get('status')=='ask':return fields.get('question','Which application did you mean?')
        payload=fields
    if isinstance(payload,str):
        try:payload=json.loads(payload)
        except (ValueError,TypeError):pass
    if isinstance(payload,dict):
        state=payload.get('status','')
        if state=='failed':return 'I could not open '+plan['label']+'. '+str(payload.get('reason') or payload.get('error') or 'Check that it is installed.')[:180]
        if state=='done':
            if str(payload.get('redirected','')).lower()=='true':
                return plan['label']+' redirected to '+str(payload.get('opened') or 'another page')+'.'
            loaded=str(payload.get('load_verified','')).lower()=='true'
            if payload.get('evidence')=='page_loaded' and loaded:
                return plan['label']+' has loaded.'
            if payload.get('evidence')=='browser_tab_url':
                return plan['label']+' is open in a browser tab.'
            return plan['label']+' is open.'
        if state=='unverified':return 'I could not confirm opening '+plan['label']+'. '+str(payload.get('reason') or 'Check the browser window.')[:180]
        return 'Opening '+plan['label']+'.'
    text=str(payload or '')
    if text.startswith('Opened'):return 'Sent '+plan['label']+' to your browser.'
    return text[:280] or 'I could not confirm the launch.'
