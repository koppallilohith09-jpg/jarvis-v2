import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
from core.gestures import GestureService
from core.gesture_preview import GesturePreview
from test_gestures import hand

class PreviewTests(unittest.TestCase):
    def setUp(self):
        guard=patch('core.input_stop.register_stop',return_value=True)
        guard.start();self.addCleanup(guard.stop)
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        # Qt's offscreen plugin has no Windows font discovery in this runner.
        from PyQt6.QtGui import QFontDatabase
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    def test_remote_landmark_view_and_closing_disarms(self):
        service=GestureService();service.arm('remote',True);service.feed(hand(),'remote',service.generation,0)
        window=GesturePreview(service);window.show();self.app.processEvents();window.refresh()
        self.assertIn('Windows control ON',window.title.text());self.assertIn('Point',window.detected.text())
        window.grab().save('gesture-view-check.png')
        window.close();self.assertFalse(service.control);self.assertEqual(service.preview()['landmarks'],())
    def test_preview_buffer_is_bounded_cleared_and_ignores_expired_session(self):
        service=GestureService();service.arm('remote');service.mode='pc';gen=service.generation
        frame=b'\x22\x88\xcc'*16
        service.publish_frame(frame,4,4,gen)
        self.assertEqual(service.preview()['frame'][0],frame)
        window=GesturePreview(service);window.show();self.app.processEvents();window.close()
        self.assertIsNone(service.preview()['frame'])
        service.publish_frame(frame,4,4,gen);self.assertIsNone(service.preview()['frame'])
        with self.assertRaises(ValueError):service.publish_frame(b'bad',4,4,gen)

if __name__=='__main__':unittest.main()
