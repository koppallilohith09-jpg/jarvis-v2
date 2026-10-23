"""Real async DNS/TLS checks against provider APIs, without keys or generation.

The expected responses are authentication failures. Only statuses and timings
are recorded; no profile, API key, prompt, or response body is read or saved.
"""
import asyncio,json,sys,time
from pathlib import Path
import httpx
from core.local_privacy import gemini_access,openai_access,install_network_guard,audit_network

async def verify():
    async def request(name,url,scope,expected):
        started=time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20,connect=10),trust_env=False,follow_redirects=False) as client:
                with scope():response=await client.get(url)
            return {'provider':name,'status':response.status_code,'expected_auth_status':expected,
                'passed':response.status_code==expected,'seconds':round(time.monotonic()-started,3)}
        except Exception as error:
            return {'provider':name,'passed':False,'error_type':type(error).__name__,
                'seconds':round(time.monotonic()-started,3)}
    checks=await asyncio.gather(
        request('Gemini','https://generativelanguage.googleapis.com/v1beta/models',gemini_access,403),
        request('OpenAI','https://api.openai.com/v1/models',openai_access,401))
    outside=False
    try:await asyncio.get_running_loop().getaddrinfo('generativelanguage.googleapis.com',443)
    except PermissionError:outside=True
    raw_ip=False
    with gemini_access():
        try:audit_network('socket.connect',(None,('192.0.2.100',443)))
        except PermissionError:raw_ip=True
    return {'checks':checks,'external_dns_blocked_outside_request':outside,
        'unresolved_external_ip_blocked_inside_request':raw_ip,
        'keys_or_generation_used':False,'passed':outside and raw_ip and all(item['passed'] for item in checks)}

def main():
    install_network_guard()
    report=asyncio.run(verify())
    root=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    (root/'network-diagnostics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    if not report['passed']:raise RuntimeError('Unauthenticated provider DNS/TLS check failed; see network-diagnostics.json.')

if __name__=='__main__':main()
