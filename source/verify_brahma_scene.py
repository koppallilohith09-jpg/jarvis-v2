"""Exercise the real embedded WebGL view. Never accesses a camera or microphone."""
import os,sys,json,time
from pathlib import Path

def main():
    print('Starting embedded 3D check',flush=True)
    os.environ['QT_QPA_PLATFORM']='windows' if '--desktop' in sys.argv else 'offscreen'
    os.environ.pop('JARVIS_OFFSCREEN_STATIC',None)
    if '--desktop' not in sys.argv:os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS','--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader --disable-gpu-compositing')
    from PyQt6.QtCore import Qt,qInstallMessageHandler
    def qt_log(kind,context,message):
        with Path('scene-qt.log').open('a',encoding='utf-8') as log:log.write(message+'\n')
    qInstallMessageHandler(qt_log)
    from PyQt6.QtWidgets import QApplication
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts,True)
    app=QApplication.instance() or QApplication([sys.argv[0]])
    from PyQt6.QtGui import QFontDatabase
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    print('Qt application ready',flush=True)
    from ui import MainWindow
    print('UI imported',flush=True)
    from core.gestures import ROOT
    window=MainWindow('face.png');print('Window created',flush=True);window.resize(1440,900);window.show()
    scene=window._unified.orb
    def spin(predicate,timeout=45):
        until=time.monotonic()+timeout
        while time.monotonic()<until:
            app.processEvents();time.sleep(.02)
            if predicate():return
        raise TimeoutError('WebGL check timed out: '+scene.caption.text())
    def js(script):
        result=[];scene.page.runJavaScript(script,lambda value:result.append(value));spin(lambda:bool(result));return result[0]
    try:
        spin(lambda:scene.ready)
        window._unified.motion.setChecked(False);scene.reduced=False;scene.refresh()
        first=js('window.__ORB__.getState()')
        shared=(ROOT/'share-edition.json').is_file()
        if shared:assert first.get('originalScene') and not first.get('referenceScene'),first
        else:assert first.get('referenceScene') and first.get('sceneOrigin')=='Brahma Echo',first
        spin(lambda:js('window.__ORB__.getState().simTime')>first['simTime'])
        scene.state='THINKING';scene.set_audio_level(.6);scene.refresh()
        spin(lambda:js('window.__ORB__.getState().bridgeState')=='THINKING')
        start_radius=js('window.__ORB__.getState().targetRadius')
        js("document.querySelector('canvas').dispatchEvent(new WheelEvent('wheel',{deltaY:-400,clientX:200,clientY:200,bubbles:true,cancelable:true}))")
        spin(lambda:js('window.__ORB__.getState().radius')<start_radius*.98)
        js('window.__ORB__.reset()');spin(lambda:abs(js('window.__ORB__.getState().radius')-start_radius)<0.1)
        js('window.__ORB__.zoom(0.4)');spin(lambda:js('window.__ORB__.getState().radius')<start_radius*0.6)
        js('window.__ORB__.reset()');spin(lambda:abs(js('window.__ORB__.getState().radius')-start_radius)<0.1)
        assert not js('window.__ORB__.getState().errors')
        scene.reduced=True;scene.refresh();spin(lambda:js('window.__ORB__.getState().externalPaused'))
        paused=js('window.__ORB__.getState()')
        scene.reduced=False;scene.state='IDLE';scene.set_audio_level(0);scene.refresh()
        spin(lambda:not js('window.__ORB__.getState().externalPaused'))
        window._muted=True;scene.muted=True;window._unified.refresh()
        window._unified.operation.setText('Preview of the actual 3D desktop UI. Camera and microphone are off.')
        window._unified.chat.add('YOU','Enable eye control',True)
        window._unified.chat.add('JARVIS','Eye control is available in Modes. Allow its local camera preview, then calibrate before enabling the pointer.')
        for _ in range(10):app.processEvents();time.sleep(.05)
        window.grab().save(str(ROOT/'jarvis-monochrome-preview.png'))
        window._unified.navigate('modes');app.processEvents();window.grab().save(str(ROOT/'jarvis-monochrome-modes.png'))
        assert not scene.guard.blocked,scene.guard.blocked
        report={'embedded_qt_webgl':'passed','reference_scene':'Original JARVIS globe' if shared else 'Brahma Echo website','wheel_listener':'passed','zoom_into_core_and_reset':'passed','animated_rendering':'passed','assistant_state_bridge':'passed','reduce_motion_pause_resume':'passed','blocked_requests':scene.guard.blocked,'scene':js('window.__ORB__.getState()'),'camera_microphone':'not accessed'}
        (ROOT/'brahma-scene-diagnostics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report).encode('ascii','backslashreplace').decode())
    finally:
        window.close();scene.page.deleteLater();app.processEvents()

if __name__=='__main__':
    try:main()
    except BaseException:
        import traceback
        Path('scene-exception.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
