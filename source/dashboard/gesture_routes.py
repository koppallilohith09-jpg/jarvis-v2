"""Paired devices send authenticated, encrypted landmark data; never video."""
import hashlib
import json
import sys
from pathlib import Path
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

def install(app, server, authenticated, service=None):
    if service is None:
        from core.gestures import service
    root=Path(__file__).resolve().parent.parent
    assets=(Path(sys.executable).parent if getattr(sys,'frozen',False) else root)/'models/web'

    @app.get('/gestures',response_class=HTMLResponse)
    async def page():
        return HTMLResponse((root/'dashboard/static/gestures.html').read_text(encoding='utf-8'),headers={'Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; media-src 'self' blob:; frame-ancestors 'none'"})

    @app.get('/gesture-client.js')
    async def client():
        return FileResponse(root/'dashboard/static/gesture-client.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

    @app.get('/gesture-assets/{name:path}')
    async def asset(name:str):
        if name not in {'vision_bundle.mjs','hand_landmarker.task','wasm/vision_wasm_internal.js','wasm/vision_wasm_internal.wasm','wasm/vision_wasm_nosimd_internal.js','wasm/vision_wasm_nosimd_internal.wasm'}:
            return JSONResponse({'error':'Not found'},404)
        target=assets/name
        if not target.is_file():return JSONResponse({'error':'Local hand assets missing. Run Prepare-Local.ps1 on the PC.'},503)
        mime='application/wasm' if name.endswith('.wasm') else 'text/javascript' if name.endswith(('.js','.mjs')) else 'application/octet-stream'
        return FileResponse(target,media_type=mime)

    @app.get('/api/gestures/status')
    async def status(req:Request):
        if not authenticated(req):return JSONResponse({'error':'Unauthorized'},401)
        return JSONResponse(service.status(),headers={'Cache-Control':'no-store'})

    @app.post('/api/gestures/stop')
    async def stop(req:Request):
        if not authenticated(req):return JSONResponse({'error':'Unauthorized'},401)
        service.stop()
        return JSONResponse({'ok':True})

    @app.post('/api/gestures')
    async def frame(req:Request):
        if not authenticated(req):return JSONResponse({'error':'Unauthorized'},401)
        data=bytearray()
        async for part in req.stream():
            data.extend(part)
            if len(data)>12000:return JSONResponse({'error':'Frame too large'},413)
        try:
            body=json.loads(data)
            token=req.headers.get('authorization','').removeprefix('Bearer ').strip()
            if not isinstance(body,dict) or not isinstance(body.get('enc'),str):raise ValueError('Encrypted frame required.')
            clear=server._decrypt(token,body['enc'])
            if clear is None:raise ValueError('Decryption failed.')
            payload=json.loads(clear)
            if not isinstance(payload,dict):raise ValueError('Invalid frame.')
            events=service.feed(payload.get('landmarks'),'remote',payload.get('generation'),payload.get('seq'),actor=hashlib.sha256(token.encode()).hexdigest())
            return JSONResponse({'ok':True,'gesture':service.status()['gesture'],'events':events})
        except (ValueError,TypeError,KeyError) as error:
            return JSONResponse({'error':str(error)[:200]},400)
