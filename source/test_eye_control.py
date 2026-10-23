import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace
import numpy as np
from core.eye_control import Calibration,Dwell,EyeService,eye_features
from core.camera_lease import claim,release

def face(x=0,y=0,closed=False):
    p=[[.5,.5,0.] for _ in range(478)]
    for a,b,top,bottom,iris,cx in ((33,133,159,145,468,.35),(362,263,386,374,473,.65)):
        p[a]=[cx-.08,.5,0];p[b]=[cx+.08,.5,0]
        gap=.001 if closed else .028;p[top]=[cx,.5-gap,0];p[bottom]=[cx,.5+gap,0];p[iris]=[cx+x*.16,.5+y*.16,0]
    return p

class EyeTests(unittest.TestCase):
    def test_iris_motion_and_blink_pause(self):
        a=eye_features(face());b=eye_features(face(.1,.05))
        self.assertGreater(b[0],a[0]);self.assertGreater(b[1],a[1]);self.assertIsNone(eye_features(face(closed=True)))
        self.assertIsNone(eye_features([]));p=face();p[468][0]=float('nan');self.assertIsNone(eye_features(p))
    def test_calibration_maps_movement_and_rejects_constant_data(self):
        c=Calibration();xy=[(x,y) for y in (.12,.5,.88) for x in (.12,.5,.88)]
        features=[eye_features(face((x-.5)*.3,(y-.5)*.25)) for x,y in xy]
        self.assertLess(c.fit(features,xy),.05)
        self.assertTrue(np.allclose(c.predict(eye_features(face(.06,-.05))),(.7,.3),atol=.04))
        with self.assertRaises(ValueError):Calibration().fit([features[0]]*9,xy)
    def test_dwell_only_once_until_move(self):
        d=Dwell();self.assertFalse(d.feed((.5,.5),0));self.assertTrue(d.feed((.5,.5),1.5));self.assertFalse(d.feed((.5,.5),5))
        self.assertFalse(d.feed((.8,.8),6));self.assertTrue(d.feed((.8,.8),7.5));d.reset();self.assertFalse(d.feed((.8,.8),9))
    def test_preview_and_face_loss_never_click(self):
        e=EyeService();e._act=Mock();e.feed(face());e.feed([],10)
        self.assertIsNone(e.feature);e._act.assert_not_called()
        with self.assertRaises(ValueError):e.set_control(True)
    def test_camera_lease(self):
        claim('test')
        try:
            with self.assertRaises(ValueError):claim('other')
            release('other')
            with self.assertRaises(ValueError):claim('other')
        finally:release('test')
    def test_face_loss_releases_drag_and_resets_dwell(self):
        e=EyeService();e._release_drag=Mock();e.dwell.feed((.5,.5),0);e.feed([])
        e._release_drag.assert_called_once();self.assertIsNone(e.dwell.anchor)
    def test_head_fallback_moves_without_gaze_calibration_and_stops_on_face_loss(self):
        e=EyeService();e.active=True;mouse=SimpleNamespace(size=lambda:(1920,1080),moveTo=Mock())
        with patch.dict('sys.modules',{'pyautogui':mouse}),patch('core.input_stop.register_stop',return_value=True):
            e.feed(face());e.set_head_control(True)
            points=face();points[1][0]+=.05;e.feed(points)
            self.assertEqual(e.pointer_mode,'head');self.assertLess(e.position[0],.5);mouse.moveTo.assert_called_once()
            self.assertIsNone(e.calibration.weights)
            mouse.moveTo.reset_mock();e.feed([]);mouse.moveTo.assert_not_called()
            e.stop();self.assertFalse(e.control)

if __name__=='__main__':unittest.main()
