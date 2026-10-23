"""Windows per-user DPAPI protection for secrets inside configuration JSON."""
import base64
import ctypes
from ctypes import wintypes
import json
import os

PREFIX='dpapi:v1:'

class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]

def _crypt(text,decode=False):
    if os.name!='nt': raise RuntimeError('Saving/decrypting credentials requires Windows DPAPI in this adaptation.')
    raw=base64.b64decode(text[len(PREFIX):],validate=True) if decode else text.encode('utf-8')
    buffer=ctypes.create_string_buffer(raw)
    source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    if decode:
        fn=crypt.CryptUnprotectData
        fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        ok=fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target))
    else:
        fn=crypt.CryptProtectData
        fn.argtypes=[ctypes.POINTER(Blob),wintypes.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
        ok=fn(ctypes.byref(source),'JARVIS local credentials',None,None,None,1,ctypes.byref(target))
    fn.restype=wintypes.BOOL
    if not ok: raise OSError('Windows credential protection failed; no plaintext secret was saved.')
    try:
        result=ctypes.string_at(target.data,target.size)
        return result.decode('utf-8') if decode else PREFIX+base64.b64encode(result).decode('ascii')
    finally:
        kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
        kernel.LocalFree(target.data)

def _secret(key):
    key=key.lower()
    return key in ('api_key','password','client_secret','access_token','refresh_token','auth_token') or key.endswith(('_api_key','_password','_secret'))

def transform(value,decode=False,key=''):
    if isinstance(value,dict): return {k:transform(v,decode,k) for k,v in value.items()}
    if isinstance(value,list): return [transform(v,decode,key) for v in value]
    if _secret(key) and isinstance(value,str) and value:
        if decode: return _crypt(value,True) if value.startswith(PREFIX) else value
        return value if value.startswith(PREFIX) else _crypt(value)
    return value

def dumps(value,**kwargs): return json.dumps(transform(value),**kwargs)

def loads(text): return transform(json.loads(text),decode=True)

def initialize_config(path):
    from core.local_privacy import default_config
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(dumps(default_config(),indent=2),encoding='utf-8')
    else:
        # Migrate in place without creating another plaintext-key backup.
        data=loads(path.read_text(encoding='utf-8'))
        protected=dumps(data,indent=2)
        temp=path.with_suffix('.protected.tmp')
        temp.write_text(protected,encoding='utf-8');temp.replace(path)
