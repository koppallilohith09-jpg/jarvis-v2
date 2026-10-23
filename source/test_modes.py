import asyncio,os,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from core.mode_commands import parse_mode
from providers.engine_pipeline import PipelineEngine
from test_quick_commands import FakeLLM

class Parse(unittest.TestCase):
    def test_explicit_mode_requests(self):
        for command,mode,action in [('enable eye control','eyes','enable'),('Jarvis, switch to gestures','gestures','enable'),('pair my ipad','devices','pair'),('calibrate my eyes','eyes','calibrate'),('enable dwell clicks','eyes','dwell'),('stop all cameras','assistant','stop')]:
            self.assertEqual(parse_mode(command),{'mode':mode,'action':action})
    def test_conversation_and_compound_requests_do_not_activate(self):
        for text in ['explain eye control','enable eye control and delete files','I want to learn about gestures','open youtube']:
            self.assertIsNone(parse_mode(text))

class Pipeline(unittest.IsolatedAsyncioTestCase):
    async def test_mode_commands_use_ui_handler_without_llm(self):
        e=PipelineEngine(FakeLLM());seen=[]
        async def mode(spec):seen.append(spec);return 'Modes are on screen.'
        e.on_mode_command=mode
        await e.send_client_content(turns={'parts':[{'text':'enable eye control'}]});await e._gen
        self.assertEqual(seen,[{'mode':'eyes','action':'enable'}]);self.assertEqual(e._llm.calls,0);await e.close()

class Desktop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ['QT_QPA_PLATFORM']='offscreen'
        os.environ['JARVIS_OFFSCREEN_STATIC']='1'
        cls.temp=tempfile.TemporaryDirectory();os.environ['JARVIS_DATA_DIR']=cls.temp.name
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QFontDatabase
        cls.app=QApplication.instance() or QApplication([]);QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_dashboard_and_mode_request_do_not_silently_open_camera(self):
        from ui import MainWindow
        from core.eye_control import service as eyes
        window=MainWindow('face.png');window.show();self.app.processEvents()
        with patch.object(eyes,'start') as start:
            result=window._unified.request({'mode':'eyes','action':'enable'});self.app.processEvents()
            self.assertIn('confirm',result);start.assert_not_called();self.assertIsNotNone(window._unified.pending)
            window._unified.request({'mode':'pending','action':'cancel'});self.assertIsNone(window._unified.pending)
        window._unified.navigate('devices');self.app.processEvents();self.assertIn('off',window._unified.device_status.text())
        window.close()

    def test_stop_cancels_delayed_camera_start(self):
        from ui import MainWindow
        from core.eye_control import service as eyes
        window=MainWindow('face.png');callbacks=[]
        with patch('core.unified_shell.QTimer.singleShot',side_effect=lambda delay,callback:callbacks.append(callback)),patch.object(eyes,'start') as start:
            window._unified.activate('eyes')
            window._unified.stop_everything()
            for callback in callbacks:callback()
            start.assert_not_called()
        window.close()

if __name__=='__main__':unittest.main()
