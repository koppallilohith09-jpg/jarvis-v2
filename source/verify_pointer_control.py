"""Exercise actual Qt controls -> tracking services -> mocked Windows input.

No camera, microphone, real pointer movement or real clicking is used.
"""
import json,os,sys,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np

def hand():
    p=[[.5,.65,0.] for _ in range(21)];p[0]=[.5,.9,0.];p[4]=[.2,.6,0.]
    for base,pip,tip,x in ((5,6,8,.4),(9,10,12,.5),(13,14,16,.6),(17,18,20,.7)):
        p[base]=[x,.7,0.];p[pip]=[x,.5,0.];p[tip]=[x,.7,0.]
    p[8]=[.4,.2,0.];return p

def face(x=0,y=0):
    p=[[.5,.5,0.] for _ in range(478)]
    for a,b,top,bottom,iris,cx in ((33,133,159,145,468,.35),(362,263,386,374,473,.65)):
        p[a]=[cx-.08,.5,0];p[b]=[cx+.08,.5,0]
        p[top]=[cx,.472,0];p[bottom]=[cx,.528,0];p[iris]=[cx+x*.16,.5+y*.16,0]
    return p

def main():
    from PyQt6.QtWidgets import QApplication,QWidget
    from PyQt6.QtCore import Qt
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts,True)
    app=QApplication.instance() or QApplication([sys.argv[0]])
    from core.gestures import service as hands
    from core.eye_control import service as eyes,eye_features
    from core.gesture_panel import open_panel
    from core.gesture_preview import GesturePreview
    from core.eye_panel import CalibrationView,TARGETS,VALIDATE
    mouse=SimpleNamespace(size=lambda:(1920,1080),position=lambda:(960,540),moveTo=Mock(),click=Mock(),scroll=Mock(),press=Mock())
    owner=QWidget();panel=None;preview=None;cal=None
    hands.stop();eyes.stop()
    try:
        with patch.dict(sys.modules,{'pyautogui':mouse}),patch('core.input_stop.register_stop',return_value=True):
            hands.arm('remote');gen=hands.generation
            panel=open_panel(owner);app.processEvents()
            assert panel.control.isEnabled(),'Pointer checkbox must remain enabled during preview.'
            panel.control.setChecked(True);assert hands.control and hands.generation==gen
            hands.feed(hand(),'remote',gen,0,now=10);hands.feed(hand(),'remote',gen,1,now=10.2)
            mouse.moveTo.assert_not_called() # first stable point anchors to the current cursor
            moved=hand();moved[8][0]=.35
            hands.feed(moved,'remote',gen,2,now=10.24)
            assert mouse.moveTo.called and mouse.moveTo.call_args.args[0]>960
            preview=GesturePreview(hands);preview.refresh();assert preview.control.isChecked()
            preview.control.setChecked(False);assert not hands.control
            mouse.moveTo.reset_mock();hands.feed(hand(),'remote',gen,3,now=10.4);hands.feed(hand(),'remote',gen,4,now=10.6)
            mouse.moveTo.assert_not_called()
            preview.control.setChecked(True);assert hands.control
            preview.close();assert hands.mode=='off'

            eyes.active=True;cal=CalibrationView(auto_start=False);cal.timer.stop();cal.start_button.click()
            assert not eyes.snapshot()['calibrated']
            xy=TARGETS
            features=[eye_features(face((x-.5)*.3,(y-.5)*.25)) for x,y in xy]
            eyes.calibration.fit(features,xy)
            try:eyes.set_control(True)
            except ValueError:pass
            else:raise AssertionError('Unvalidated eye calibration must not enable input.')
            cal.begin();cal.started=time.monotonic()-2
            with patch.object(eyes,'sample_count',return_value=3),patch.object(eyes,'capture') as capture:
                cal.tick();assert cal.index==0;capture.assert_not_called()
                assert '3/8' in cal.hint
            for i,(x,y) in enumerate(TARGETS+VALIDATE):
                cal.started=time.monotonic()-2
                with patch.object(eyes,'sample_count',return_value=8),patch.object(eyes,'capture',return_value=eye_features(face((x-.5)*.3,(y-.5)*.25))):cal.tick()
                if i<12:assert not eyes.snapshot()['calibrated']
            assert eyes.snapshot()['calibrated'];assert not cal.enable_button.isHidden()
            cal.enable_button.click();assert eyes.control
            eyes.feed(face(.06,-.05));assert mouse.moveTo.called
            mouse.moveTo.reset_mock();eyes.set_control(False);eyes.feed(face(.06,-.05));mouse.moveTo.assert_not_called()
            eyes.calibration.weights=None;eyes.calibration.validated=False;eyes.feed(face());eyes.set_head_control(True)
            moved=face();moved[1][0]+=.05;eyes.feed(moved)
            assert eyes.pointer_mode=='head' and eyes.position[0]<.5 and mouse.moveTo.called
            mouse.moveTo.reset_mock();eyes.feed([]);mouse.moveTo.assert_not_called()
        report={'hand_preview_to_control_without_camera_restart':'passed','separate_preview_pointer_toggle':'passed','hand_landmarks_reach_windows_input_adapter':'passed (mocked input)','slow_eye_calibration_waits_for_samples':'passed','eye_validation_required_before_input':'passed','calibration_enable_button_to_eye_input_adapter':'passed (mocked input)','head_fallback_without_gaze_calibration':'passed (mocked input)','disable_blocks_movement':'passed','physical_camera_and_windows_pointer':'not accessed'}
        root=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent
        (root/'pointer-control-diagnostics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))
    finally:
        hands.stop();eyes.stop()
        for item in (cal,preview,panel,owner):
            if item:item.close()
        app.processEvents()

if __name__=='__main__':main()
