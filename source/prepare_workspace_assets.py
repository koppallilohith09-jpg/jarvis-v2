"""Explicit one-time public asset download. No runtime model downloads."""
from pathlib import Path
import hashlib,json,shutil,urllib.request
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parent
def main():
    manifest=json.loads((ROOT/'holo/upstream-assets.json').read_text())
    def fetch(item):
        target=ROOT/'holo'/item['path'];target.parent.mkdir(parents=True,exist_ok=True)
        url=f"https://raw.githubusercontent.com/{manifest['repo']}/{manifest['commit']}/{item['path']}"
        data=urllib.request.urlopen(url,timeout=120).read()
        assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==item['sha'],item['path']
        target.write_bytes(data);return item['path']
    with ThreadPoolExecutor(max_workers=4) as pool:
        for name in pool.map(fetch,manifest['assets']):print(name,flush=True)
    # Reuse the already verified 0.10.21 local browser model/WASM stack.
    source=ROOT/'models/web';vendor=ROOT/'holo/vendor'
    print([p.name for p in source.iterdir()],flush=True)
    shutil.copy2(source/'vision_bundle.mjs',vendor/'vision_bundle.mjs')
    shutil.copytree(source/'wasm',vendor/'wasm',dirs_exist_ok=True)
    shutil.copy2(ROOT/'models/hand_landmarker.task',vendor/'hand_landmarker.task')
    face=ROOT/'models/face_landmarker.task'
    url='https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'
    if not face.exists():face.write_bytes(urllib.request.urlopen(url,timeout=120).read())
    (ROOT/'models/face-source.json').write_text(json.dumps({'url':url,'sha256':hashlib.sha256(face.read_bytes()).hexdigest()},indent=2))
    print('Offline workspace and face assets ready.',flush=True)
if __name__=='__main__':main()
