"""Windows camera backend fallback and bounded transient-frame retries."""
import sys,time

class VideoClock:
    """One strictly increasing millisecond clock per MediaPipe detector."""
    def __init__(self):self.last=-1
    def next(self):
        self.last=max(self.last+1,int(time.monotonic()*1000))
        return self.last
def open_camera(index):
    import cv2
    backends=(cv2.CAP_DSHOW,cv2.CAP_MSMF,cv2.CAP_ANY) if sys.platform=='win32' else (cv2.CAP_ANY,)
    for backend in backends:
        camera=cv2.VideoCapture(index,backend)
        if camera.isOpened():
            camera.set(cv2.CAP_PROP_FRAME_WIDTH,640);camera.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
            camera.set(cv2.CAP_PROP_FPS,30);camera.set(cv2.CAP_PROP_BUFFERSIZE,1)
            for _ in range(12):
                ok,frame=camera.read()
                if ok and frame is not None:return camera
                time.sleep(.05)
        camera.release()
    raise RuntimeError('Webcam unavailable. Close other camera apps and check Windows camera access.')
def read_frame(camera,stop_event):
    for _ in range(12):
        if stop_event.is_set():return None
        ok,frame=camera.read()
        if ok and frame is not None:return frame
        stop_event.wait(.05)
    raise RuntimeError('Webcam stopped supplying frames. Stop and select another camera index.')
