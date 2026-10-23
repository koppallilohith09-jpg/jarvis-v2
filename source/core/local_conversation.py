"""Small offline conversational intents and input-echo rejection."""
import re

def greeting(text):
    if not isinstance(text,str):return None
    value=' '.join(re.findall(r'\w+',text.casefold()))
    if re.fullmatch(r'(?:(?:hello|hi|hey|good morning|good afternoon|good evening)(?: (?:there|jarvis|mark|brahma))?|(?:jarvis|mark|brahma))',value):
        return "Hello. I'm here. What can I help you with?"
    return None

def input_echo(answer,question):
    if not isinstance(question,str):return False
    if re.search(r'\b(repeat|echo|say exactly|read aloud|read this)\b',question,re.I):return False
    normalize=lambda value:' '.join(re.findall(r'\w+',str(value).casefold()))
    return bool(normalize(question)) and normalize(answer)==normalize(question)
