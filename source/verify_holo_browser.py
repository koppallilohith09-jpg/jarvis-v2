"""Holo's actual gesture engine and local WASM; synthetic camera only."""
import json,tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from core.holo_workspace import Workspace
from memory.local_database import LocalDatabase

def main():
    with tempfile.TemporaryDirectory() as folder:
        db=LocalDatabase(Path(folder)/'test.sqlite3');file=Path(folder)/'cedar.txt';file.write_text('Cedar\nPrivate local note.');db.import_document(file)
        workspace=Workspace(db);url=workspace.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True,args=['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
                page=browser.new_page(viewport={'width':1360,'height':920});errors=[];requests=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('console',lambda msg:print('CONSOLE',msg.type,msg.text.encode('ascii','backslashreplace').decode(),flush=True) if msg.type=='error' else None)
                page.on('request',lambda request:requests.append(request.url))
                page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(url+'/') else route.abort())
                page.add_init_script("""
                    window.cameraCalls=0;
                    navigator.mediaDevices.getUserMedia=async()=>{
                        window.cameraCalls++;
                        const canvas=document.createElement('canvas');canvas.width=640;canvas.height=480;
                        const ctx=canvas.getContext('2d');setInterval(()=>{ctx.fillStyle='black';ctx.fillRect(0,0,640,480)},70);
                        window.testStream=canvas.captureStream(12);return window.testStream;
                    };
                """)
                page.goto(url+'/?session='+workspace.secret)
                page.wait_for_function("() => document.querySelectorAll('.orb').length>0")
                assert page.evaluate('window.cameraCalls')==0
                assert page.locator('#status').inner_text().startswith('Camera off')
                page.locator('#retry').click()
                try:page.wait_for_function("() => document.querySelector('#status').textContent.includes('hands live')",timeout=30000)
                except Exception:
                    print('STATUS',page.locator('#status').inner_text().encode('ascii','backslashreplace').decode(),flush=True)
                    print('DIAG',getattr(workspace,'last_event',{}),errors,flush=True);raise
                page.wait_for_timeout(1500)
                page.locator('#retry').click();page.wait_for_function("() => window.testStream.getTracks().every(t=>t.readyState==='ended')")
                page.screenshot(path=str(Path(__file__).parent/'holo-page-check.png'))
                camera_errors=list(errors);assert not camera_errors,camera_errors
                probe=browser.new_page(viewport={'width':1360,'height':920})
                probe.route('**/*',lambda route:route.continue_() if route.request.url.startswith(url+'/') else route.abort())
                probe.on('console',lambda msg:print('PROBE',msg.text.encode('ascii','backslashreplace').decode()) if 'PROBE' in msg.text.upper() else None)
                probe.goto(url+'/?probe=1&session='+workspace.secret)
                probe.wait_for_function("() => document.title.startsWith('PROBE ')",timeout=60000)
                state=probe.evaluate("() => ({title:document.title,body:document.body.innerText.slice(-4500)})")
                assert state['title'].startswith('PROBE 26/26'),state['title']
                assert all(address.startswith(url+'/') for address in requests)
                report={'local_holo_page':'passed','no_camera_until_click':'passed','local_wasm_inference':'passed','stop_releases_synthetic_camera':'passed','external_requests':0,'probe':state,'page_errors':errors,'physical_hands':'not tested in this check'}
                (Path(__file__).parent/'holo-diagnostics.json').write_text(json.dumps(report,indent=2));print(json.dumps(report).encode('ascii','backslashreplace').decode());browser.close()
        finally:workspace.stop()
if __name__=='__main__':main()
