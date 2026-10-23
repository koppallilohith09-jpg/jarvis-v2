"""Isolated headless browser check with a synthetic camera, no device camera."""
import json
import threading
import time
from pathlib import Path
import urllib.request
import uvicorn
from playwright.sync_api import sync_playwright
from dashboard.server import DashboardServer
from core.gestures import service

ROOT=Path(__file__).resolve().parent
server=DashboardServer();server._tokens['browser-test']=time.time();server._token_keys['browser-test']='SYNTHETIC-PAIRING-KEY'
service.arm('remote',False)
http=uvicorn.Server(uvicorn.Config(server.app,host='127.0.0.1',port=18767,log_level='error'))
thread=threading.Thread(target=http.run,daemon=True);thread.start()
for _ in range(80):
    if http.started:break
    time.sleep(.05)
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
        page=browser.new_page(viewport={'width':820,'height':1180})
        errors=[];requests=[];frames=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:requests.append(request.url))
        page.on('response',lambda response:frames.append(response.status) if response.url.endswith('/api/gestures') else None)
        page.route('**/*',lambda route:route.continue_() if route.request.url.startswith('http://127.0.0.1:18767/') else route.abort())
        page.add_init_script("""
          sessionStorage.setItem('jarvis_token','browser-test');
          sessionStorage.setItem('jarvis_key','SYNTHETIC-PAIRING-KEY');
          navigator.mediaDevices.getUserMedia=async()=>{
            const canvas=document.createElement('canvas');canvas.width=640;canvas.height=480;
            const ctx=canvas.getContext('2d');
            setInterval(()=>{ctx.fillStyle='black';ctx.fillRect(0,0,640,480);},70);
            window.testStream=canvas.captureStream(12);return window.testStream;
          };
        """)
        page.goto('http://127.0.0.1:18767/gestures')
        page.get_by_role('button',name='Start iPad camera',exact=True).click()
        page.wait_for_function("() => document.querySelector('#status').textContent.includes('No hand visible')",timeout=90000)
        page.screenshot(path=str(ROOT/'gesture-page-check.png'),full_page=True)
        page.get_by_role('button',name='Stop camera and PC gestures',exact=True).click()
        page.wait_for_function("() => window.testStream.getTracks().every(t=>t.readyState==='ended')")
        assert service.mode=='off'
        assert frames and all(code==200 for code in frames),frames
        assert not errors,errors
        assert all(url.startswith('http://127.0.0.1:18767/') for url in requests),requests
        report={'browser':'headless Edge','local_wasm_inference':'passed','encrypted_frames':len(frames),'stop_releases_synthetic_camera':'passed','external_requests':0,'physical_ipad':'not tested'}
        (ROOT/'browser-diagnostics.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report));browser.close()
finally:
    service.stop();http.should_exit=True;thread.join(timeout=5)
