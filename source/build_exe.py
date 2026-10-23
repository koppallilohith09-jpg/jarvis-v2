"""Reproducible portable folder build; config credentials are never copied."""
from pathlib import Path
import shutil
import subprocess
import sys
import os
import hashlib,json

ROOT=Path(__file__).resolve().parent
VERSION='1.8.2'
RELEASE=ROOT/'dist'/VERSION

def main():
    def snapshot():
        result={}
        for folder,dirs,files in os.walk(ROOT):
            dirs[:]=[name for name in dirs if name not in ('build','dist','references','vendor_brahma','__pycache__','.git','preview-data')]
            for name in files:
                path=Path(folder)/name
                if path.suffix=='.py' or path.is_relative_to(ROOT/'assets'):
                    result[path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
        return result
    sources=snapshot()
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--windowed','--onedir','--name','JARVIS-Local-Gestures','--distpath',str(RELEASE),'--workpath',str(ROOT/'build'),'--specpath',str(ROOT/'build')]
    for package in ('core','memory','providers','dashboard','actions'):
        command+=['--collect-submodules',package]
    for package in ('mediapipe','onnxruntime','kokoro_onnx','espeakng_loader','faster_whisper','ctranslate2','sounddevice','uvicorn','websockets'):
        command+=['--collect-all',package]
    for module in ('main','verify_brahma_scene','verify_pointer_control','verify_voice_response','verify_conversation','verify_cloud','verify_network','verify_camera','verify_share','verify_launch','docx','pptx','openpyxl','reportlab','PyPDF2','pyautogui','pyperclip','google.genai','PyQt6.QtMultimedia','PyQt6.QtMultimediaWidgets','PyQt6.QtWebEngineCore','PyQt6.QtWebEngineWidgets','python_multipart'):
        command+=['--hidden-import',module]
    for package in ('torch','tensorflow','jax','jaxlib','IPython','pytest','tkinter'):
        command+=['--exclude-module',package]
    for folder in ('actions','plugins'):
        command+=['--add-data',f'{ROOT/folder};{folder}']
    command+=['--add-data',f'{ROOT/"dashboard/static"};dashboard/static']
    command+=[str(ROOT/'launcher.py')]
    # The workspace's Poppler directory carries an ICU DLL with versioned
    # exports. Qt needs Windows' unversioned ICU API. Do not let the build
    # resolve Qt's system dependency to that unrelated helper on PATH.
    environment=dict(os.environ)
    environment['PATH']=os.pathsep.join(path for path in environment.get('PATH','').split(os.pathsep) if 'poppler' not in path.lower())
    subprocess.run(command,cwd=ROOT,env=environment,check=True)
    if sources!=snapshot():raise RuntimeError('Source files changed during packaging. Rebuild the final saved source before releasing.')
    out=RELEASE/'JARVIS-Local-Gestures'
    # This Python distribution's SSLContext requires its CA distrust file
    # beside frozen ssl.py. Retain the runtime's certificate policy unchanged.
    import ssl
    cert=Path(ssl.__file__).with_name('codex-rejected-cas.pem')
    if cert.is_file():shutil.copy2(cert,out/'_internal'/cert.name)
    shutil.copytree(ROOT/'models',out/'models',dirs_exist_ok=True,ignore=shutil.ignore_patterns('.cache'))
    shutil.copytree(ROOT/'holo',out/'holo',dirs_exist_ok=True)
    shutil.copytree(ROOT/'assets/echo-core',out/'assets/echo-core',dirs_exist_ok=True)
    shutil.copytree(ROOT/'assets/echo-reference',out/'assets/echo-reference',dirs_exist_ok=True,ignore=shutil.ignore_patterns('preview.png'))
    if (out/'models/ollama').exists() or (out/'runtime').exists():raise RuntimeError('Offline AI must not be included.')
    (out/'core').mkdir(exist_ok=True)
    shutil.copy2(ROOT/'core/prompt.txt',out/'core/prompt.txt')
    for name in ('LICENSE','UPSTREAM.json','GESTURES.md','Enable-iPad.ps1',f'RELEASE-{VERSION}.md'):
        shutil.copy2(ROOT/name,out/name)
    (out/'Start-Gestures.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\nstart "" "JARVIS-Local-Gestures.exe" --gestures-only\r\n')
    (out/'Check-App.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\n"JARVIS-Local-Gestures.exe" --self-test\r\n')
    if (ROOT/'requirements-local.lock.txt').is_file():shutil.copy2(ROOT/'requirements-local.lock.txt',out/'requirements-local.lock.txt')
    # Check the actual portable build, including DLLs, not just Python source.
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        subprocess.run([str(out/'JARVIS-Local-Gestures.exe'),'--self-test'],cwd=out,env={**environment,'JARVIS_DATA_DIR':temp},check=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (out/'build-manifest.json').write_text(json.dumps({'version':VERSION,'edition':'personal','scene':'Brahma Echo reference; attribution and license retained','exe_sha256':hashlib.sha256((out/'JARVIS-Local-Gestures.exe').read_bytes()).hexdigest(),'source_sha256':sources},indent=2),encoding='utf-8')
    print(out/'JARVIS-Local-Gestures.exe')

if __name__=='__main__':main()
