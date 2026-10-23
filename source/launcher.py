"""Windows launcher, log capture, and noninteractive packaged diagnostics."""
import os
from pathlib import Path
import sys

ROOT=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent

def diagnostics():
    os.environ['JARVIS_OFFSCREEN_STATIC']='1'
    import json
    import asyncio
    import numpy as np
    import mediapipe as mp
    from core.gestures import GestureGate
    from PyQt6.QtWidgets import QApplication,QWidget
    from PyQt6.QtCore import Qt
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts,True)
    from core.gesture_panel import open_panel
    from core.gesture_preview import GesturePreview
    from dashboard.server import DashboardServer
    from providers.tts_kokoro import KokoroTTS
    from providers.stt_whisper import WhisperSTT
    from core.secure_config import initialize_config
    initialize_config(ROOT/'config/api_keys.json')
    app=QApplication.instance() or QApplication([sys.argv[0]])
    parent=QWidget();panel=open_panel(parent);app.processEvents();panel.close();app.processEvents()
    from core.gestures import GestureService
    preview_service=GestureService();preview=GesturePreview(preview_service);preview.show();app.processEvents();preview.close()
    from ui import MainWindow
    window=MainWindow('face.png');app.processEvents()
    from PyQt6.QtWidgets import QPushButton
    assert set(window._unified.nav)=={'dashboard','chat','modes','devices','settings'}
    asset='echo-core' if (ROOT/'share-edition.json').is_file() else 'echo-reference'
    assert (ROOT/'assets'/asset/'index.html').is_file()
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from core.eye_panel import EyePanel
    eyes=EyePanel(window);eyes.show();app.processEvents();eyes.close()
    window.close()
    dashboard=DashboardServer()
    assert any(route.path=='/api/gestures' for route in dashboard.app.routes)
    model=ROOT/'models/hand_landmarker.task'
    options=mp.tasks.vision.HandLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),num_hands=1)
    with mp.tasks.vision.HandLandmarker.create_from_options(options) as detector:
        result=detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB,data=np.zeros((256,256,3),dtype=np.uint8)))
        assert not result.hand_landmarks
    options=mp.tasks.vision.FaceLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_path=str(ROOT/'models/face_landmarker.task')),num_faces=1)
    with mp.tasks.vision.FaceLandmarker.create_from_options(options) as detector:
        result=detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB,data=np.zeros((256,256,3),dtype=np.uint8)))
        assert not result.face_landmarks
    import tempfile
    from memory.local_database import LocalDatabase
    from core.holo_workspace import Workspace
    with tempfile.TemporaryDirectory() as folder:
        store=LocalDatabase(Path(folder)/'memory.sqlite3');sid=store.session();store.add_message(sid,'user','My name is Local Test.')
        assert LocalDatabase(store.path).facts()[0]['value']=='Local Test'
        deck=Workspace(store);url=deck.start()
        import urllib.request
        request=urllib.request.Request(url+'/api/tree',headers={'X-Holo-Session':deck.secret})
        assert json.loads(urllib.request.urlopen(request,timeout=5).read())[0]['name']=='LOCAL NOTES'
        deck.stop()
        from core.local_capabilities import write_document,ProductivityStore
        import time
        os.environ['JARVIS_DATA_DIR']=str(Path(folder)/'data')
        try:
            for fmt,content in [('docx','# Test\nLocal content.'),('pdf','Local content.'),('pptx','# First\nLocal content.'),('xlsx','Item,Cost\nBooks,200')]:
                path=write_document(fmt,'Local test',content);assert path.is_file() and path.stat().st_size>100
            calendar=ProductivityStore(store);item=calendar.add('Local test',time.time()+3600)
            assert ProductivityStore(LocalDatabase(store.path)).events()[0]['id']==item
        finally:os.environ.pop('JARVIS_DATA_DIR',None)
    for relative in ('holo.html','vendor/vision_bundle.mjs','vendor/wasm/vision_wasm_internal.wasm','vendor/three.module.js','props/apollo-11-module.glb'):
        assert (ROOT/'holo'/relative).is_file(),relative
    from providers.tts_system import SystemTTS
    native_wav=SystemTTS({'voice':'Microsoft David Desktop'})._synth_blocking('Ready.')
    assert len(native_wav)>100
    pcm,rate=KokoroTTS({})._synth('Gesture control is ready.')
    assert pcm and rate==24000
    speech,elapsed=WhisperSTT({})._load_blocking()
    import main as assistant
    result={'version':'1.8.2','qt_panel':'passed','separate_gesture_preview':'passed','eye_panel':'passed','holo_local_server_and_assets':'passed','sqlite_restart':'passed','unified_shell':'passed','office_pdf_generation':'passed','persistent_calendar':'passed','webengine_import_and_scene_asset':'passed; rendering checked separately with --verify-ui','dashboard_routes':'passed','hand_model_inference':'passed','face_model_inference':'passed','windows_native_wav_bytes':len(native_wav),'kokoro_pcm_bytes':len(pcm),'whisper_model':'passed','assistant_import':'passed','network_policy':'local_only','camera_test':'not performed','eye_physical_calibration':'requires user','ipad_physical_test':'not performed'}
    (ROOT/'diagnostics.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))

def main():
    os.chdir(ROOT)
    if '--configure-ipad' in sys.argv:
        from urllib.parse import urlparse
        from core.secure_config import initialize_config,loads,dumps
        address=sys.argv[sys.argv.index('--configure-ipad')+1].rstrip('/')
        parsed=urlparse(address)
        if parsed.scheme!='https' or not (parsed.hostname or '').endswith('.ts.net') or parsed.username or parsed.password or parsed.port or parsed.path:
            raise ValueError('Use your private HTTPS Tailscale hostname.')
        path=ROOT/'config/api_keys.json';initialize_config(path)
        cfg=loads(path.read_text(encoding='utf-8'));cfg.update(dashboard_enabled=True,dashboard_https=False,dashboard_external_url=address)
        path.write_text(dumps(cfg,indent=2),encoding='utf-8');return
    from core.local_privacy import install_network_guard
    install_network_guard()
    if any(flag in sys.argv for flag in ('--self-test','--verify-ui','--verify-pointer','--verify-voice','--verify-conversation','--verify-cloud','--verify-share','--verify-network','--verify-camera','--verify-launch')):
        if getattr(sys,'frozen',False):
            log=(ROOT/'diagnostics-output.log').open('w',encoding='utf-8',buffering=1)
            sys.stdout=log;sys.stderr=log
        os.environ['QT_QPA_PLATFORM']='offscreen'
        (ROOT/'diagnostics-error.log').unlink(missing_ok=True)
        try:
            if '--verify-launch' in sys.argv:
                from verify_launch import main as check_launch
                check_launch()
            elif '--verify-network' in sys.argv:
                from verify_network import main as check_network
                check_network()
            elif '--verify-camera' in sys.argv:
                from verify_camera import main as check_camera
                check_camera()
            elif '--verify-cloud' in sys.argv:
                from verify_cloud import main as check_cloud
                check_cloud()
            elif '--verify-share' in sys.argv:
                from verify_share import main as check_share
                check_share()
            elif '--verify-conversation' in sys.argv:
                from verify_conversation import main as check_conversation
                check_conversation()
            elif '--verify-voice' in sys.argv:
                from verify_voice_response import main as check_voice
                check_voice()
            elif '--verify-pointer' in sys.argv:
                from verify_pointer_control import main as check_pointer
                check_pointer()
            elif '--verify-ui' in sys.argv:
                from verify_brahma_scene import main as check_ui
                sys.argv.append('--desktop');check_ui()
            else:diagnostics()
        except Exception:
            import traceback
            (ROOT/'diagnostics-error.log').write_text(traceback.format_exc(),encoding='utf-8')
            sys.exit(1)
        return
    logs=ROOT/'logs';logs.mkdir(exist_ok=True)
    log=(logs/'desktop.log').open('a',encoding='utf-8',buffering=1)
    sys.stdout=log;sys.stderr=log
    try:
        from core.secure_config import initialize_config
        initialize_config(ROOT/'config/api_keys.json')
        if '--gestures-only' in sys.argv:
            from PyQt6.QtWidgets import QApplication,QWidget
            from core.gesture_panel import open_panel
            from core.gestures import service
            from dashboard.server import DashboardServer
            import asyncio,threading
            app=QApplication(sys.argv);app.aboutToQuit.connect(service.stop)
            owner=QWidget();panel=open_panel(owner)
            dashboard=DashboardServer()
            threading.Thread(target=lambda:asyncio.run(dashboard.serve()),daemon=True).start()
            def pair():
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(panel,'Pair iPad',f'Open {dashboard.get_url()}/login on your iPad.\nPairing code: {dashboard.new_key()}\nThen open Gestures on the dashboard.')
            from PyQt6.QtWidgets import QPushButton
            button=QPushButton('Show iPad pairing code');button.setMinimumHeight(44);button.clicked.connect(pair);panel.layout().addWidget(button)
            app.exec()
        else:
            import main as assistant
            assistant.main()
    except Exception:
        import traceback
        traceback.print_exc()
        if '--self-test' not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,f'JARVIS could not start. Details are in:\n{logs / "desktop.log"}','JARVIS startup',16)
        raise

if __name__=='__main__':main()
