"""A separate loopback-only Holo deck, backed by user-imported SQLite notes."""
import atexit,json,mimetypes,secrets,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,unquote
from core.gestures import ROOT

class Workspace:
    def __init__(self,store=None):
        if store is None:
            from memory.local_database import database
            store=database()
        self.store=store;self.secret=secrets.token_urlsafe(32);self.server=None;self.thread=None;self.camera_until=0;self.camera_revoked=False
    def release_camera(self):
        from core.camera_lease import release
        self.camera_until=0;release('Holo workspace')
    def tree(self):
        notes=[{'name':str(row['id']),'title':row['title'],'body':row['body'][:420],'full':row['body'][:50000]} for row in self.store.documents(24)]
        if not notes:
            notes=[{'name':'welcome','title':'Your local workspace','body':'Import a TXT or Markdown file in JARVIS, then reload this deck. Pinch to grab, two hands to stretch and rotate.','full':'This deck displays only files you explicitly import into the JARVIS local database. Mouse controls work with the camera off. Start camera enables local hand tracking. The crush gesture shows an excerpt; ask JARVIS to analyse it using your connected AI.'}]
        return [{'kind':'folder','name':'LOCAL NOTES','files':notes}]
    def start(self):
        if self.server:return self.url
        owner=self;root=(ROOT/'holo').resolve()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,code,body,kind='application/json'):
                data=body if isinstance(body,bytes) else json.dumps(body).encode()
                self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
                self.send_header('Content-Security-Policy',"default-src 'self' blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; connect-src 'self' blob:; img-src 'self' data: blob:; media-src 'self' blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
                self.end_headers();self.wfile.write(data)
            def valid_host(self):return self.headers.get('Host')==urlsplit(owner.url).netloc
            def authorised(self):
                return self.valid_host() and secrets.compare_digest(self.headers.get('X-Holo-Session',''),owner.secret) and self.headers.get('Origin',owner.url)==owner.url
            def do_GET(self):
                if not self.valid_host():return self.send(403,{'error':'Invalid local host'})
                path=unquote(urlsplit(self.path).path)
                if path.startswith('/api/'):
                    if not self.authorised():return self.send(401,{'error':'Open this workspace from the JARVIS app.'})
                    if path=='/api/tree':return self.send(200,owner.tree())
                    if path=='/api/props':return self.send(200,['apollo-11-module.glb','triceratops.glb'])
                    if path=='/api/alive':return self.send(200,{'ok':True})
                    return self.send(404,{})
                if path in ('/','/holo.html'):
                    token=parse_qs(urlsplit(self.path).query).get('session',[''])[0]
                    # The static deck is harmless without an API session. Browser reload
                    # retains its token in sessionStorage; no query token is required then.
                    file=root/'holo.html'
                elif path.startswith(('/vendor/','/props/')):
                    file=(root/path.lstrip('/')).resolve()
                    if not file.is_relative_to(root) or not file.is_file() or file.suffix not in ('.js','.mjs','.wasm','.task','.glb'):return self.send(404,{})
                else:return self.send(404,{})
                if not file.is_file():return self.send(404,{'error':'Local workspace asset missing'})
                mime={'.mjs':'text/javascript','.js':'text/javascript','.wasm':'application/wasm','.glb':'model/gltf-binary','.html':'text/html; charset=utf-8'}.get(file.suffix,'application/octet-stream')
                return self.send(200,file.read_bytes(),mime)
            def do_POST(self):
                if not self.authorised():return self.send(401,{'error':'Invalid local workspace session'})
                path=urlsplit(self.path).path
                if path=='/api/camera/start':
                    try:
                        from core.camera_lease import claim
                        claim('Holo workspace');owner.camera_revoked=False;owner.camera_until=time.monotonic()+6
                        return self.send(200,{'ok':True})
                    except ValueError as error:return self.send(409,{'error':str(error)})
                if path=='/api/camera/heartbeat':
                    if owner.camera_revoked or not owner.camera_until:return self.send(409,{'error':'Camera stopped from JARVIS.'})
                    owner.camera_until=time.monotonic()+6;return self.send(200,{'ok':True})
                if path=='/api/camera/stop':owner.release_camera();return self.send(200,{'ok':True})
                if path not in ('/api/state','/api/diag'):return self.send(404,{})
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=8192:return self.send(413,{})
                    value=json.loads(self.rfile.read(length))
                    if not isinstance(value,dict):raise ValueError()
                    # UI diagnostics stay in memory, never camera frames or disk logs.
                    owner.last_event=value
                    return self.send(200,{'ok':True})
                except (ValueError,UnicodeError):return self.send(400,{})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.url=f'http://127.0.0.1:{self.server.server_address[1]}'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True,name='local-holo-workspace');self.thread.start()
        def lease_watch():
            while self.server:
                if self.camera_until and time.monotonic()>self.camera_until:self.release_camera()
                time.sleep(1)
        threading.Thread(target=lease_watch,daemon=True,name='holo-camera-lease').start()
        atexit.register(self.stop);return self.url
    def stop(self):
        self.release_camera()
        if self.server:self.server.shutdown();self.server.server_close();self.server=None

_workspace=None
def stop_camera():
    if _workspace:
        _workspace.camera_revoked=True;_workspace.release_camera()
def open_workspace(parent=None):
    import webbrowser
    global _workspace
    if _workspace is None:_workspace=Workspace()
    address=_workspace.start()+'/?session='+_workspace.secret
    webbrowser.open(address,new=1)
    return _workspace

