"""Local tools and speech, with scoped HTTPS access to the selected AI provider.

This is an application policy, not an OS sandbox for hostile native extensions.
Model/dependency downloads are a separate explicit setup operation.
"""
import ipaddress
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import urlsplit

_installed=False
_openai_request=ContextVar('jarvis_openai_request',default=False)

class _ProviderRequest:
    __slots__=('host','addresses','active')
    def __init__(self,host):
        self.host=host
        self.addresses=set()
        self.active=True

def _host(value):
    if isinstance(value,bytes):value=value.decode('ascii',errors='ignore')
    return str(value).lower().rstrip('.')

def _ip(value):
    try:return ipaddress.ip_address(str(value).split('%',1)[0]).compressed
    except ValueError:return None

def _remember_provider_addresses(host,results):
    request=_openai_request.get()
    if request and request.active and _host(host)==request.host:
        request.addresses.update(address for result in results
            if result[1]==1 and (address:=_ip(result[4][0])) is not None)

def _resolve_in_context(host,port,family=0,type=0,proto=0,flags=0):
    import socket
    results=socket.getaddrinfo(host,port,family,type,proto,flags)
    _remember_provider_addresses(host,results)
    return results

def _preserve_async_dns_context():
    """asyncio normally drops ContextVars when resolving DNS in its executor.

    Copy the caller's context into that worker, just as asyncio.to_thread does.
    The request's existing host/port restrictions still apply; no ambient host
    allowlist or permission is granted to unrelated tasks or threads.
    """
    import asyncio
    try:loop=asyncio.get_running_loop()
    except RuntimeError:return
    if getattr(loop,'_jarvis_dns_context',False):return
    async def resolve(host,port,*,family=0,type=0,proto=0,flags=0):
        return await asyncio.to_thread(_resolve_in_context,host,port,family,type,proto,flags)
    loop.getaddrinfo=resolve
    loop._jarvis_dns_context=True

@contextmanager
def gemini_access():
    _preserve_async_dns_context()
    request=_ProviderRequest('generativelanguage.googleapis.com')
    token=_openai_request.set(request)
    try:yield
    finally:
        request.active=False
        _openai_request.reset(token)

@contextmanager
def openai_access():
    """Narrow request scope; ordinary tools retain the local-only policy."""
    _preserve_async_dns_context()
    request=_ProviderRequest('api.openai.com')
    token=_openai_request.set(request)
    try:yield
    finally:
        request.active=False
        _openai_request.reset(token)

def require_loopback_url(value):
    parsed=urlsplit(value if '://' in value else 'http://'+value)
    if parsed.scheme not in ('http','https') or parsed.username or parsed.password:
        raise ValueError('Strict local mode requires a loopback model URL without embedded credentials.')
    host=parsed.hostname or ''
    if host=='localhost': return
    try: allowed=ipaddress.ip_address(host.strip('[]')).is_loopback
    except ValueError: allowed=False
    if not allowed: raise ValueError('Strict local mode blocks remote AI endpoints. Use 127.0.0.1 on this PC.')

def validate_provider(provider_id,cfg):
    if provider_id in ('openai_cloud','gemini_cloud'):
        if cfg.get('cloud_enabled') is not True:raise ValueError('Enable the selected cloud AI in the connection form first.')
        if not str(cfg.get('api_key','')).strip():raise ValueError('Enter your own API key in JARVIS Settings.')
        return
    if provider_id=='cloud_setup':return
    if provider_id=='whisper':
        if cfg.get('backend','local')!='local': raise ValueError('Strict local mode requires on-device Whisper.')
    elif provider_id not in ('kokoro','piper','system_tts','pipeline'):
        raise ValueError('This provider is disabled in strict local mode: '+provider_id)

def _loopback(host):
    if isinstance(host,bytes): host=host.decode('ascii',errors='ignore')
    if host in ('localhost','127.0.0.1','::1'): return True
    try: return ipaddress.ip_address(str(host).strip('[]')).is_loopback
    except ValueError: return False

def audit_network(event,args):
    if event in ('socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr'):
        host=_host(args[0])
        permitted=_openai_request.get()
        if permitted and permitted.active and host==permitted.host:return
        if not _loopback(args[0]): raise PermissionError('Strict local mode blocked external DNS/network access.')
    elif event in ('socket.connect','socket.sendto'):
        address=args[-1]
        permitted=_openai_request.get()
        if (event=='socket.connect' and permitted and permitted.active
            and isinstance(address,tuple) and len(address)>1 and address[1]==443
            and _ip(address[0]) in permitted.addresses):return
        if isinstance(address,tuple) and not _loopback(address[0]):
            raise PermissionError('Strict local mode blocked an external Python network request.')

def install_network_guard():
    global _installed
    if not _installed:
        import functools,socket
        original=socket.getaddrinfo
        @functools.wraps(original)
        def resolve(host,port,*args,**kwargs):
            results=original(host,port,*args,**kwargs)
            _remember_provider_addresses(host,results)
            return results
        socket.getaddrinfo=resolve
        sys.addaudithook(audit_network)
        _installed=True

def default_config():
    import platform
    return {'os_system':platform.system().lower(),'privacy_mode':'cloud_ai_local_speech',
        'dashboard_enabled':False,'dashboard_https':False,'morning_brief_enabled':False,
        'providers':{'mode':'pipeline','pipeline':{'stt':'whisper','llm':'cloud_setup','tts':'system_tts'},
          'sidecar':'cloud_setup','sidecar_first':True,'creds':{
            'whisper':{'backend':'local','model':'base','device':'cpu','language':'en'},'kokoro':{'voice':'bm_george','speed':1},'system_tts':{'voice':'Microsoft David Desktop'}}}}
