"""Clean cloud-only portable edition. Never copies the working user profile."""
from pathlib import Path
import hashlib,json,os,re,shutil,subprocess,sys,tempfile,zipfile
ROOT=Path(__file__).resolve().parent
VERSION='1.8.2'
OUTPUT=ROOT/'dist'/f'JARVIS-{VERSION}-Friend'
ROOT_FILES=('JARVIS-Local-Gestures.exe','Check-App.cmd','Start-Gestures.cmd','Enable-iPad.ps1','LICENSE','UPSTREAM.json','GESTURES.md','requirements-local.lock.txt',f'RELEASE-{VERSION}.md')
SOURCE_DIRS=('actions','core','dashboard','memory','plugins','providers')
def sha(path):
    result=hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda:handle.read(8*1024*1024),b''):result.update(block)
    return result.hexdigest()
def source_copy():
    target=OUTPUT/'source';target.mkdir()
    for directory in SOURCE_DIRS:
        for path in (ROOT/directory).rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts:continue
            relative=path.relative_to(ROOT)
            allowed=(path.suffix=='.py' or relative.as_posix() in ('core/prompt.txt','core/face_model.obj')
                     or (relative.parts[:2]==('dashboard','static') and path.suffix in ('.html','.js','.css')))
            if allowed:
                destination=target/relative;destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(path,destination)
    for path in ROOT.glob('*.py'):
        if path.name in ('prepare_echo_reference.py','inspect_bundle.py','check_webcam_local.py','test_local_memory.py','measure_local_voice.py') or path.name.startswith('verify_physical_'):continue
        shutil.copy2(path,target/path.name)
    for name in ('requirements.txt','requirements-local.lock.txt','LICENSE','UPSTREAM.json'):
        shutil.copy2(ROOT/name,target/name)
def audit(path):
    parts=path.relative_to(OUTPUT).parts;lowered={part.lower() for part in parts}
    if lowered & {'brahma-core','echo-reference','ollama','ollama-cpu','vendor_brahma'} or (parts[0]!='_internal' and lowered & {'config','logs','references','preview-data','__pycache__','.git','uploads','exports'}):
        raise ValueError('Private or removed content found: '+str(path.relative_to(OUTPUT)))
    if path.name.lower() in ('api_keys.json','openai-connection.json','long_term.json','.env') or path.name.lower().startswith('.env.') or path.suffix.lower() in ('.sqlite','.sqlite3','.db','.log','.key','.pfx'):
        raise ValueError('Personal data file found: '+str(path.relative_to(OUTPUT)))
    if path.suffix.lower() in ('.py','.json','.txt','.md','.html','.js','.cmd','.ps1') and path.stat().st_size<2_000_000:
        if re.search(rb'(?:sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{30,}|dpapi:v1:[A-Za-z0-9+/=]{32,})',path.read_bytes()):
            raise ValueError('Potential API secret in '+str(path.relative_to(OUTPUT)))
def main():
    built=ROOT/'dist'/VERSION/'JARVIS-Local-Gestures'
    if not (built/'build-manifest.json').exists():raise RuntimeError('Build the final EXE first.')
    OUTPUT.mkdir(exist_ok=False)
    for directory in ('_internal','models','holo','core'):
        shutil.copytree(built/directory,OUTPUT/directory,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.cache'))
    shutil.copytree(built/'assets/echo-core',OUTPUT/'assets/echo-core')
    for name in ROOT_FILES:shutil.copy2(built/name,OUTPUT/name)
    source_copy()
    (OUTPUT/'share-edition.json').write_text(json.dumps({'version':VERSION,'artwork':'Original interactive layered globe','default_ai':'Cloud connection required; no offline AI','private_brahma_asset':False},indent=2))
    (OUTPUT/'README-FIRST.txt').write_text('''JARVIS 1.8.2 - Windows x64 portable friend edition

1. Extract the ENTIRE ZIP to a writable folder. Double-click
   JARVIS-Local-Gestures.exe. Keep all support folders together.
2. Settings > AI connection: choose Gemini or OpenAI and enter YOUR OWN key.
   Gemini: accept the data-use notice, then Test & connect. The check only lists
   models, without generating a reply. Use Check available Gemini models if your
   model is unavailable. Chat still requires network and available quota.
   Gemini free-tier availability depends on your Google project. Keep paid
   billing off if you want no API charges. Free-tier data may improve Google
   products. OpenAI needs API credit; ChatGPT subscriptions do not pay API fees.
3. No Qwen weights, Ollama runtime or offline AI fallback are installed.
   Whisper hearing, Windows/Kokoro voice, hand/face detection and SQLite storage
   run locally. These speech and camera models are included.
4. Hold Hold to talk while speaking, then release to send, or type a command.
   Try hello Jarvis, open youtube, or attach a TXT and ask it to analyse it.
   AI questions and file analysis need your cloud connection.
5. Drag the globe to rotate. Wheel/pinch or + / - zoom inside the core. Reset
   restores the view. Amber switches color; White restores monochrome.
6. Modes > Hand gestures: start the camera and enable Windows pointer control.
   Raise only your index finger to move. Pinch to click. Raise index and middle
   fingers together and move vertically to scroll. Open palm pauses.
   Returning your hand to the frame anchors at the CURRENT cursor without a
   jump. Choose Precise, Balanced or Fast sensitivity. Ctrl+Alt+G stops input.
7. Pure webcam eye tracking is experimental and failed the earlier physical
   validation. Head-assisted pointer is available. Remote iPad access is OFF
   until separately configured with private HTTPS pairing.
8. No personal profile, keys, chats or documents from the creator are included.
   Your new local memory stays in your Windows JARVIS profile. When connected,
   chat and relevant memory/file text go to your selected AI provider.

9. This release fixes scoped cloud DNS and camera timestamp/session failures.
   App launches announce completion after observing a visible matching window.
   Supported native browsers can confirm the foreground tab URL; managed browser
   sessions can also verify the page loaded. An unavailable accessibility signal
   is reported as unverified. Redirects are reported as redirects.

This modified Mark-LVI build includes Holo components and original globe artwork.
Use personally and noncommercially under the included upstream license. See
LICENSE, THIRD-PARTY-NOTICES.txt, source/, RELEASE-1.8.2.md and component licenses.
''',encoding='utf-8')
    (OUTPUT/'THIRD-PARTY-NOTICES.txt').write_text('''Modified integration source is in source/. Exact Python versions are in
requirements-local.lock.txt. Retained component notices and licenses apply.

Mark-LVI: FatihMakes, CC BY-NC 4.0; see LICENSE and UPSTREAM.json.
https://github.com/FatihMakes/Mark-LVI
Holo Gestures: Zubair Trabzada / AI Workshop Studio LLC, MIT; see holo/LICENSE
and holo/THIRD_PARTY.md, including model and prop credits.
https://github.com/zubair-trabzada/holo-gestures
The globe's original scene code uses the MIT three.js runtime; see
assets/echo-core/NOTICE.txt and LICENSE-three.txt. Restricted Brahma assets and
website scripts are excluded.
Kokoro, eSpeak NG and phonemizer: models/kokoro/ licenses and notices.
https://github.com/espeak-ng/espeak-ng
https://github.com/bootphon/phonemizer
MediaPipe, Whisper, PyQt/Qt and remaining dependencies: retained model licenses,
_internal package metadata and upstream notices.
''',encoding='utf-8')
    print('Clean edition copied; checking packaged EXE.',flush=True)
    with tempfile.TemporaryDirectory() as temp:
        environment={**os.environ,'JARVIS_DATA_DIR':str(Path(temp)/'data')}
        for flag in ('--self-test','--verify-share','--verify-launch','--verify-cloud','--verify-pointer','--verify-camera','--verify-ui'):
            subprocess.run([str(OUTPUT/'JARVIS-Local-Gestures.exe'),flag],cwd=OUTPUT,env=environment,check=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            print(flag+' passed',flush=True)
        reports={}
        for name in ('diagnostics.json','share-diagnostics.json','launch-confirmation-diagnostics.json','cloud-diagnostics.json','pointer-control-diagnostics.json','camera-stability-diagnostics.json','brahma-scene-diagnostics.json'):
            reports[name]=json.loads((OUTPUT/name).read_text(encoding='utf-8'))
        (ROOT/'dist'/f'friend-verification-{VERSION}.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
    for name in ('config','logs'):
        path=(OUTPUT/name).resolve()
        if not path.is_relative_to(OUTPUT.resolve()):raise ValueError('Invalid cleanup path')
        if path.exists():shutil.rmtree(path)
    for pattern in ('*.log','*diagnostics*.json','friend-edition-preview.png','jarvis-monochrome-*.png'):
        for path in OUTPUT.glob(pattern):path.unlink()
    (OUTPUT/'share-manifest.json').write_text(json.dumps({'version':VERSION,'edition':'friend','exe_sha256':sha(OUTPUT/'JARVIS-Local-Gestures.exe'),'offline_llm':'absent','artwork':'original JARVIS globe; private Echo scene excluded','cloud_live_test':'not performed; requires user key and quota'},indent=2))
    files=sorted(path for path in OUTPUT.rglob('*') if path.is_file())
    for path in files:audit(path)
    archive=OUTPUT.parent/(OUTPUT.name+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as package:
        for path in files:
            package.write(path,Path(OUTPUT.name)/path.relative_to(OUTPUT),compress_type=zipfile.ZIP_STORED if path.stat().st_size>8_000_000 else zipfile.ZIP_DEFLATED)
    print('ZIP created; reading every entry to check CRC integrity.',flush=True)
    with zipfile.ZipFile(archive) as package:
        broken=package.testzip()
        if broken:raise RuntimeError('ZIP integrity failure: '+broken)
    (archive.with_suffix('.zip.sha256.txt')).write_text(sha(archive)+'  '+archive.name+'\n')
    print(json.dumps({'zip':str(archive),'bytes':archive.stat().st_size,'files':len(files),'crc':'passed','profile_files':'excluded','offline_ai':'absent'},indent=2),flush=True)
if __name__=='__main__':main()
