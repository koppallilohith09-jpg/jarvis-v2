"""Explicit online setup. The running assistant never downloads these assets."""
import base64
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import requests

ROOT=Path(__file__).resolve().parent
VERSION='0.10.21'
MODEL='https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'

def get(url):
    response=requests.get(url,timeout=180);response.raise_for_status();return response.content

def main():
    root=ROOT/'models';web=root/'web';web.mkdir(parents=True,exist_ok=True)
    model=root/'hand_landmarker.task'
    if not model.exists():model.write_bytes(get(MODEL))
    shutil.copy2(model,web/model.name)
    metadata=json.loads(get(f'https://registry.npmjs.org/@mediapipe/tasks-vision/{VERSION}'))
    blob=get(metadata['dist']['tarball'])
    algorithm,digest=metadata['dist']['integrity'].split('-',1)
    if algorithm!='sha512' or base64.b64encode(hashlib.sha512(blob).digest()).decode()!=digest:raise RuntimeError('MediaPipe package integrity mismatch.')
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as archive:
        names=['vision_bundle.mjs','wasm/vision_wasm_internal.js','wasm/vision_wasm_internal.wasm','wasm/vision_wasm_nosimd_internal.js','wasm/vision_wasm_nosimd_internal.wasm']
        for name in names:
            target=web/name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(archive.extractfile('package/'+name).read())
        for member in archive.getmembers():
            if member.name.lower() in ('package/license','package/license.txt','package/notice'):
                (web/Path(member.name).name).write_bytes(archive.extractfile(member).read())
    kokoro=ROOT.parent/'jarvis-desktop/native/models/kokoro'
    if kokoro.exists():shutil.copytree(kokoro,root/'kokoro',dirs_exist_ok=True)
    hashes={str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and p.name!='assets.json'}
    (root/'assets.json').write_text(json.dumps({'hand_model_url':MODEL,'web_package':VERSION,'npm_integrity':metadata['dist']['integrity'],'sha256':hashes},indent=2))
    print('Local hand models, iPad inference files and available Kokoro assets prepared.')

if __name__=='__main__':main()
