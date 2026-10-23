"""Explicit voice/text mode requests. No model guess controls a camera."""
import re
def parse_mode(text):
    if not isinstance(text,str):return None
    text=re.sub(r'^(?:hey\s+)?jarvis[,\s:]+','',text.strip(),flags=re.I).strip().casefold().rstrip('.!?')
    text=re.sub(r'^(?:(?:can|could|would) you\s+)?(?:please\s+)?','',text).removesuffix(' please').strip()
    if text in ('confirm mode','yes enable it','yes enable','allow local camera','confirm camera'):return {'mode':'pending','action':'confirm'}
    if text in ('cancel mode','cancel camera','no cancel'):return {'mode':'pending','action':'cancel'}
    if text in ('show modes','open modes','show me modes','change mode'):return {'mode':'modes','action':'open'}
    if text in ('show dashboard','open dashboard','assistant mode','switch to assistant mode','stop all modes','stop all cameras'):return {'mode':'assistant','action':'stop'}
    if re.fullmatch(r'(?:pair|connect|link)(?: with)?(?: my| the)? (?:ipad|i pad|tablet)',text):return {'mode':'devices','action':'pair'}
    if re.fullmatch(r'(?:calibrate|recalibrate)(?: my)? (?:eyes|eye control|eye pointer|gaze)',text):return {'mode':'eyes','action':'calibrate'}
    if re.fullmatch(r'(?:enable|allow|start|turn on) (?:eye pointer|eye mouse|gaze pointer)',text):return {'mode':'eyes','action':'pointer'}
    if re.fullmatch(r'(?:enable|allow|start|turn on) (?:hand pointer|hand mouse|gesture pointer|gesture mouse|hand cursor)',text):return {'mode':'gestures','action':'pointer'}
    if re.fullmatch(r'(?:enable|allow|start|turn on) (?:head control|head pointer|head mouse|head cursor|head assisted cursor)',text):return {'mode':'eyes','action':'head'}
    if re.fullmatch(r'(?:enable|allow|turn on) dwell(?: clicks?| clicking)?',text):return {'mode':'eyes','action':'dwell'}
    match=re.fullmatch(r'(enable|activate|start|open|switch to|turn on|disable|stop|turn off)\s+(?:the\s+)?(.+?)(?:\s+mode)?',text)
    if not match:return None
    command,target=match.groups()
    choices={'eye control':'eyes','eye tracking':'eyes','eyes':'eyes','gaze':'eyes','gestures':'gestures','gesture control':'gestures','hand control':'gestures','hand gestures':'gestures','holo':'holo','holographic workspace':'holo','holo workspace':'holo','ipad pairing':'devices','device pairing':'devices'}
    if target not in choices:return None
    return {'mode':choices[target],'action':'stop' if command in ('disable','stop','turn off') else 'enable'}
