"""Local webcam gaze estimation with calibration. No camera starts on import."""
from collections import deque
import math,threading,time
import numpy as np
from core.gestures import ROOT

def eye_features(points):
    if len(points)<478:return None
    p=np.array([(v.x,v.y) if hasattr(v,'x') else v[:2] for v in points],dtype=float)
    if not np.isfinite(p).all():return None
    values=[]
    for left,right,top,bottom,iris in ((33,133,159,145,468),(362,263,386,374,473)):
        a,b=p[left],p[right];axis=b-a;width=np.linalg.norm(axis)
        if width<.018:return None
        horizontal=axis/width;vertical=np.array([-horizontal[1],horizontal[0]])
        if vertical[1]<0:vertical=-vertical
        opening=abs(np.dot(p[bottom]-p[top],vertical))/width
        if opening<.12:return None  # blink / shut eye pauses input
        centre=(a+b)/2;offset=(p[iris]-centre)/width
        values.append((float(np.dot(offset,horizontal)),float(np.dot(offset,vertical))))
    gaze=np.mean(values,axis=0)
    # Head position complements the iris estimate; calibration learns the mapping.
    return np.array([gaze[0],gaze[1],p[1,0],p[1,1]],dtype=float)

class Calibration:
    def __init__(self):self.weights=None;self.validated=False
    def fit(self,features,targets):
        self.validated=False
        x=np.asarray(features,dtype=float);y=np.asarray(targets,dtype=float)
        if x.ndim!=2 or x.shape[0]<9 or x.shape[1]!=4 or y.shape!=(len(x),2) or not np.isfinite(x).all() or not np.isfinite(y).all():raise ValueError('Not enough valid calibration samples.')
        self.mean=x.mean(axis=0);self.scale=x.std(axis=0)
        if min(self.scale[:2])<.004:raise ValueError('Too little eye movement detected. Improve lighting and keep both eyes visible.')
        self.scale=np.maximum(self.scale,.005)
        design=np.column_stack([np.ones(len(x)),(x-self.mean)/self.scale])
        penalty=np.diag([0,.15,.15,.5,.5])
        weights=np.linalg.solve(design.T@design+penalty,design.T@y)
        errors=np.linalg.norm(design@weights-y,axis=1)
        if np.sqrt(np.mean(errors**2))>.18:raise ValueError('Calibration is too inconsistent. Keep your head still and follow each dot again.')
        self.weights=weights;return float(np.sqrt(np.mean(errors**2)))
    def predict(self,feature):
        if self.weights is None:raise ValueError('Calibrate eye tracking first.')
        return np.clip(np.r_[1,(np.asarray(feature)-self.mean)/self.scale]@self.weights,.004,.996)

class Dwell:
    def __init__(self,seconds=1.35,radius=.035):self.seconds=seconds;self.radius=radius;self.reset()
    def reset(self):self.anchor=None;self.since=0;self.fired=False;self.progress=0
    def feed(self,position,now):
        p=np.asarray(position)
        if self.anchor is None or np.linalg.norm(p-self.anchor)>self.radius:
            self.anchor=p.copy();self.since=now;self.fired=False;self.progress=0;return False
        self.progress=min(1,(now-self.since)/self.seconds)
        if self.progress>=1 and not self.fired:self.fired=True;return True
        return False

class EyeService:
    def __init__(self):
        self.lock=threading.RLock();self.active=False;self.control=False;self.clicks=False;self.dragging=False
        self.thread=None;self.stop_event=threading.Event();self.calibration=Calibration();self.samples=deque(maxlen=80)
        self.frame=None;self.points=();self.feature=None;self.position=None;self.seen=0;self.dwell=Dwell();self.message='Eye camera is off.';self.action='click';self._smooth=None
        self.pointer_mode='gaze';self.head_centre=None;self.head_width=.3
    def snapshot(self):
        with self.lock:
            fresh=time.monotonic()-self.seen<.4
            return {'active':self.active,'control':self.control,'pointer_mode':self.pointer_mode,'calibrated':self.calibration.weights is not None and self.calibration.validated,'message':self.message,'frame':self.frame if fresh else None,'points':self.points if fresh else (),'feature':self.feature.copy() if self.feature is not None and fresh else None,'position':self.position,'dwell':self.dwell.progress,'clicks':self.clicks,'action':self.action,'dragging':self.dragging}
    def start(self,camera_index=0):
        from core.gestures import service as hands
        from core.camera_lease import claim,release
        with self.lock:
            if self.active or (self.thread and self.thread.is_alive()):raise ValueError('Stop and wait for the previous eye camera to release.')
            if hands.mode!='off':raise ValueError('Stop hand control before starting eye control.')
            claim('eyes')
            self.active=True;self.control=False;self.clicks=False;self.calibration=Calibration();self.samples.clear();self._smooth=None
            self.pointer_mode='gaze';self.head_centre=None
            self.stop_event=threading.Event();self.message='Starting local eye preview…'
            self.thread=threading.Thread(target=self._camera,args=(camera_index,),daemon=True,name='local-eye-camera');self.thread.start()
    def set_control(self,enabled,clicks=False):
        with self.lock:
            ready=self.head_centre is not None if self.pointer_mode=='head' else self.calibration.weights is not None and self.calibration.validated
            if enabled and (not self.active or not ready):raise ValueError('Start the camera and finish gaze calibration, or choose the head-assisted cursor.')
            self.control=bool(enabled);self.clicks=bool(clicks) and self.control;self.dwell.reset();self._smooth=None
            if not enabled:self._release_drag()
            self.message=('Head-assisted cursor enabled. Move your head to steer; Ctrl+Alt+G stops.' if self.pointer_mode=='head' else 'Eye pointer enabled. Ctrl+Alt+G stops control.') if enabled else 'Preview only. Pointer control is off.'
        if enabled:
            from core.input_stop import register_stop
            if not register_stop(self.stop):
                with self.lock:self.control=False;self.clicks=False;self._release_drag()
                raise ValueError('Ctrl+Alt+G is already in use. Close the other control session before enabling eye input.')
    def set_head_control(self,enabled=True,clicks=False):
        with self.lock:
            if enabled:
                if not self.active or self.feature is None or time.monotonic()-self.seen>.5:raise ValueError('Keep both eyes and your face visible, then enable the head cursor.')
                self.head_centre=self.feature[2:4].copy()
                self.head_width=max(.12,abs(self.points[263][0]-self.points[33][0]))
                self.pointer_mode='head'
            self.set_control(enabled,clicks)
    def _release_drag(self):
        if self.dragging:
            import pyautogui as mouse
            # A held button must release even when the physical mouse is at a failsafe corner.
            try:mouse.mouseUp(_pause=False)
            except mouse.FailSafeException:
                import ctypes
                ctypes.windll.user32.mouse_event(0x0004,0,0,0,0)
            self.dragging=False
    def stop(self):
        with self.lock:
            self.stop_event.set();self.active=False;self.control=False;self.clicks=False;self._release_drag()
            self.samples.clear();self.frame=None;self.points=();self.feature=None;self.position=None;self.dwell.reset();self.message='Eye tracking stopped. Camera release requested.'
    def _act(self):
        import pyautogui as mouse
        if self.action=='right':mouse.click(button='right');self.action='click'
        elif self.action=='double':mouse.doubleClick(interval=.12);self.action='click'
        elif self.action=='drag':
            if self.dragging:self._release_drag()
            else:mouse.mouseDown();self.dragging=True
        elif self.action in ('up','down'):mouse.scroll(4 if self.action=='up' else -4)
        else:mouse.click()
    def feed(self,points,now=None):
        now=time.monotonic() if now is None else now
        feature=eye_features(points) if points else None
        with self.lock:
            self.feature=feature;self.seen=now;self.points=tuple((float(v.x),float(v.y)) if hasattr(v,'x') else tuple(v[:2]) for v in points)
            if feature is None:
                self.dwell.reset();self._smooth=None;self.position=None;self._release_drag();return
            self.samples.append((now,feature.copy()))
            if self.pointer_mode=='head':
                if self.head_centre is None:return
                delta=(feature[2:4]-self.head_centre)/self.head_width
                position=np.clip(np.array([.5-delta[0]*2,.5+delta[1]*2.5]),.004,.996)
            else:
                if self.calibration.weights is None:return
                position=self.calibration.predict(feature)
            self._smooth=position if self._smooth is None else self._smooth*.70+position*.30
            self.position=tuple(self._smooth)
            if self.control and self.active:
                import pyautogui as mouse
                mouse.FAILSAFE=True
                width,height=mouse.size();x,y=self.position
                mouse.moveTo(max(5,min(width-5,round(x*width))),max(5,min(height-5,round(y*height))),_pause=False)
                if self.clicks and self.dwell.feed(position,now):self._act()
    def capture(self,since):
        with self.lock:features=[feature for stamp,feature in self.samples if stamp>=since]
        if len(features)<8:raise ValueError('Eyes were not visible long enough. Adjust lighting or camera position and try again.')
        result=np.asarray(features)
        if np.max(np.std(result[:,:2],axis=0))>.07:raise ValueError('Eye position was unstable. Keep looking at the dot.')
        return np.median(result,axis=0)
    def sample_count(self,since):
        with self.lock:return sum(stamp>=since for stamp,_ in self.samples)
    def _camera(self,index):
        camera=None
        with self.lock:stop_event=self.stop_event
        try:
            with self.lock:
                if stop_event.is_set() or not self.active:return
            import cv2,mediapipe as mp
            from core.camera_capture import open_camera,read_frame,VideoClock
            camera=open_camera(index);clock=VideoClock()
            options=mp.tasks.vision.FaceLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_path=str(ROOT/'models/face_landmarker.task')),running_mode=mp.tasks.vision.RunningMode.VIDEO,num_faces=1,min_face_detection_confidence=.6,min_face_presence_confidence=.6,min_tracking_confidence=.6)
            with mp.tasks.vision.FaceLandmarker.create_from_options(options) as detector:
                with self.lock:
                    if stop_event.is_set() or not self.active or self.stop_event is not stop_event:return
                    self.message='Eyes preview only. Follow calibration before enabling the pointer.'
                while not stop_event.is_set():
                    frame=read_frame(camera,stop_event)
                    if frame is None:break
                    rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
                    result=detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,data=rgb),clock.next())
                    with self.lock:
                        if stop_event.is_set() or not self.active or self.stop_event is not stop_event:break
                        self.frame=(rgb.tobytes(),rgb.shape[1],rgb.shape[0])
                        self.feed(result.face_landmarks[0] if result.face_landmarks else [])
                    stop_event.wait(.045)
        except Exception as error:
            with self.lock:
                if not stop_event.is_set() and self.active and self.stop_event is stop_event:
                    self.stop();self.message='Eye control stopped: '+str(error)[:250]
        finally:
            if camera is not None:camera.release()
            from core.camera_lease import release
            release('eyes')

service=EyeService()
