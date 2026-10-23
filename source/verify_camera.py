"""Packaged worker regressions and real blank-frame VIDEO inference; no camera."""
import json,sys,unittest
from pathlib import Path
import numpy as np
from core.camera_capture import VideoClock
from test_camera_stability import CameraStability

def main():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(CameraStability)
    result=unittest.TextTestRunner().run(suite)
    if not result.wasSuccessful():raise RuntimeError('Camera worker regression checks failed.')
    import mediapipe as mp
    root=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    frame=mp.Image(image_format=mp.ImageFormat.SRGB,data=np.zeros((256,256,3),dtype=np.uint8))
    streams={}
    for kind,detector,options in (
        ('hand',mp.tasks.vision.HandLandmarker,mp.tasks.vision.HandLandmarkerOptions),
        ('face',mp.tasks.vision.FaceLandmarker,mp.tasks.vision.FaceLandmarkerOptions)):
        cfg=options(base_options=mp.tasks.BaseOptions(model_asset_path=str(root/'models'/f'{kind}_landmarker.task')),running_mode=mp.tasks.vision.RunningMode.VIDEO)
        clock=VideoClock();stamps=[]
        with detector.create_from_options(cfg) as model:
            for _ in range(12):
                stamp=clock.next();stamps.append(stamp);model.detect_for_video(frame,stamp)
        assert all(a<b for a,b in zip(stamps,stamps[1:]))
        streams[kind]={'blank_frames':12,'strictly_increasing_timestamps':True}
    report={'fake_camera_worker_checks':result.testsRun,'real_mediapipe_video_streams':streams,'camera_microphone_pointer':'not accessed','passed':True}
    (root/'camera-stability-diagnostics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
