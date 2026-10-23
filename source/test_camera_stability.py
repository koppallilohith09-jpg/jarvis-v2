"""Camera-worker regressions using fake devices, frames and detectors only.

No webcam, microphone, pointer adapter, network or saved camera footage is used.
"""
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import Mock, patch

import numpy as np

from core.camera_capture import VideoClock, read_frame
from core.camera_lease import claim, release
from core.eye_control import EyeService
from core.gestures import GestureService


class FakeCamera:
    def __init__(self):
        self.reads=0;self.releases=0
        self.frame=np.zeros((4,6,3),dtype=np.uint8)
    def read(self):
        self.reads+=1
        return True,self.frame
    def release(self):self.releases+=1


class FakeDetector:
    def __init__(self,service,kind,*,frames=10,block=False,error=None):
        self.service=service;self.kind=kind;self.frames=frames
        self.block=block;self.error=error;self.timestamps=[];self.closed=False
        self.entered=threading.Event();self.resume=threading.Event()
    def __enter__(self):return self
    def __exit__(self,*args):self.closed=True
    def detect_for_video(self,image,stamp):
        if self.timestamps and stamp<=self.timestamps[-1]:
            raise ValueError('Input timestamp must be monotonically increasing.')
        self.timestamps.append(stamp)
        if self.block:
            self.entered.set()
            if not self.resume.wait(3):raise RuntimeError('Test did not release fake inference.')
        if self.error:raise RuntimeError(self.error)
        if len(self.timestamps)>=self.frames:self.service.stop()
        return SimpleNamespace(**{self.kind+'_landmarks':[]})


class CameraStability(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        folder=self.stack.enter_context(TemporaryDirectory(prefix='jarvis-fake-camera-'))
        root=Path(folder);(root/'models').mkdir()
        (root/'models/hand_landmarker.task').touch()
        self.stack.enter_context(patch('core.gestures.ROOT',root))
        self.stack.enter_context(patch('core.input_stop.register_stop',return_value=True))
        # Accidental pointer access fails this test instead of reaching Windows.
        self.stack.enter_context(patch.dict('sys.modules',{'pyautogui':None}))
        self.camera=FakeCamera()
        self.open_camera=self.stack.enter_context(patch('core.camera_capture.open_camera',return_value=self.camera))
        cv2=SimpleNamespace(COLOR_BGR2RGB=1,cvtColor=lambda frame,conversion:frame)
        self.stack.enter_context(patch.dict('sys.modules',{'cv2':cv2}))

    def worker(self,kind,**kwargs):
        service=GestureService() if kind=='hand' else EyeService()
        detector=FakeDetector(service,kind,**kwargs)
        options=lambda **values:SimpleNamespace(**values)
        vision=SimpleNamespace(
            HandLandmarkerOptions=options,FaceLandmarkerOptions=options,
            RunningMode=SimpleNamespace(VIDEO='video'),
            HandLandmarker=SimpleNamespace(create_from_options=lambda options:detector),
            FaceLandmarker=SimpleNamespace(create_from_options=lambda options:detector))
        mp=SimpleNamespace(tasks=SimpleNamespace(BaseOptions=options,vision=vision),
                           Image=lambda **values:values,ImageFormat=SimpleNamespace(SRGB='rgb'))
        self.stack.enter_context(patch.dict('sys.modules',{'mediapipe':mp}))
        self.addCleanup(self.finish,service,detector)
        return service,detector

    @staticmethod
    def finish(service,detector):
        service.stop();detector.resume.set()
        if service.thread:service.thread.join(3)

    @staticmethod
    def start(service):
        if isinstance(service,GestureService):service.arm('pc')
        else:service.start()

    def joined_and_released(self,service,detector):
        service.thread.join(3)
        self.assertFalse(service.thread.is_alive(),'Fake camera worker did not exit.')
        self.assertEqual(self.camera.releases,1)
        self.assertTrue(detector.closed)
        # A new independent consumer must be able to claim the released lease.
        claim('test-after-camera')
        release('test-after-camera')

    def test_video_clock_repeated_and_backward_ticks_stay_strictly_increasing(self):
        clock=VideoClock()
        with patch('core.camera_capture.time.monotonic',side_effect=[20,20,20,19.9,20.001,20.01]):
            stamps=[clock.next() for _ in range(6)]
        self.assertEqual(stamps,[20000,20001,20002,20003,20004,20010])

    def test_frozen_windows_clock_keeps_hand_stream_alive_for_ten_frames(self):
        service,detector=self.worker('hand')
        with patch('core.camera_capture.time.monotonic',return_value=100):
            self.start(service);self.joined_and_released(service,detector)
        self.assertEqual(detector.timestamps,list(range(100000,100010)))
        self.assertEqual(self.camera.reads,10)
        self.assertEqual(service.message,'Gesture control stopped. Camera release requested.')
        self.assertEqual(service.mode,'off')

    def test_frozen_windows_clock_keeps_eye_stream_alive_for_ten_frames(self):
        service,detector=self.worker('face')
        with patch('core.camera_capture.time.monotonic',return_value=100):
            self.start(service);self.joined_and_released(service,detector)
        self.assertEqual(detector.timestamps,list(range(100000,100010)))
        self.assertEqual(self.camera.reads,10)
        self.assertEqual(service.message,'Eye tracking stopped. Camera release requested.')
        self.assertFalse(service.active)

    def stop_during_inference(self,kind,error):
        service,detector=self.worker(kind,block=True,error=error)
        self.start(service)
        self.assertTrue(detector.entered.wait(3),'Fake detector was never entered.')
        service.stop();stopped_message=service.message
        detector.resume.set();self.joined_and_released(service,detector)
        self.assertEqual(service.message,stopped_message)
        self.assertFalse(service.control)
        if kind=='hand':
            self.assertEqual(service.mode,'off');self.assertIsNone(service._frame)
            self.assertEqual(service._points,())
        else:
            self.assertFalse(service.active);self.assertIsNone(service.frame)
            self.assertEqual(service.points,())

    def test_hand_stop_discards_in_flight_result(self):self.stop_during_inference('hand',None)
    def test_eye_stop_discards_in_flight_result(self):self.stop_during_inference('face',None)
    def test_hand_stop_preserves_message_when_in_flight_inference_raises(self):
        self.stop_during_inference('hand','Fake detector closed during stop.')
    def test_eye_stop_preserves_message_when_in_flight_inference_raises(self):
        self.stop_during_inference('face','Fake detector closed during stop.')

    def detector_failure(self,kind):
        service,detector=self.worker(kind,error='Synthetic detector failure.')
        self.start(service);self.joined_and_released(service,detector)
        self.assertIn('Synthetic detector failure.',service.message)
        self.assertFalse(service.control)
        self.assertEqual(service.mode,'off') if kind=='hand' else self.assertFalse(service.active)

    def test_hand_actual_inference_failure_disarms_and_releases_camera(self):self.detector_failure('hand')
    def test_eye_actual_inference_failure_disarms_and_releases_camera(self):self.detector_failure('face')

    def stop_before_worker_enters(self,kind):
        service,detector=self.worker(kind)
        # The worker cannot acquire the session lock until stop has completed.
        with service.lock:self.start(service);service.stop()
        service.thread.join(3)
        self.assertFalse(service.thread.is_alive())
        self.open_camera.assert_not_called()
        claim('test-before-open');release('test-before-open')

    def test_stop_before_hand_worker_starts_releases_lease(self):self.stop_before_worker_enters('hand')
    def test_stop_before_eye_worker_starts_releases_lease(self):self.stop_before_worker_enters('face')

    def test_transient_empty_frames_retry_and_device_failure_is_bounded(self):
        camera=Mock();frame=np.zeros((2,2,3),dtype=np.uint8)
        camera.read.side_effect=[(False,None)]*3+[(True,frame)]
        stop=Mock();stop.is_set.return_value=False
        self.assertIs(read_frame(camera,stop),frame)
        self.assertEqual(camera.read.call_count,4)
        camera.read.reset_mock();camera.read.side_effect=None;camera.read.return_value=(False,None)
        with self.assertRaisesRegex(RuntimeError,'stopped supplying frames'):read_frame(camera,stop)
        self.assertEqual(camera.read.call_count,12)
        stop.is_set.return_value=True;camera.read.reset_mock()
        self.assertIsNone(read_frame(camera,stop));camera.read.assert_not_called()


if __name__=='__main__':unittest.main()
