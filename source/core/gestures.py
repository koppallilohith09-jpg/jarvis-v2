"""Opt-in hand control. Camera images stay on the device doing detection."""
import math
from pathlib import Path
import secrets
import threading
import time
import sys
from core.hand_motion import HandMotion,PROFILES

ROOT = Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent.parent

def checked_landmarks(values):
    if not isinstance(values,list) or len(values)!=21: raise ValueError('Expected 21 hand landmarks.')
    result=[]
    for point in values:
        if not isinstance(point,(list,tuple)) or len(point)!=3: raise ValueError('Invalid landmark shape.')
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in point): raise ValueError('Invalid landmark number.')
        x,y,z=point
        if not (0<=x<=1 and 0<=y<=1 and -2<=z<=2): raise ValueError('Landmark out of range.')
        result.append((float(x),float(y),float(z)))
    return result

class GestureGate:
    def __init__(self):
        self.kind='';self.since=0.;self.clicked=False;self.media_fired=False;self.scroll_y=None;self.scroll_remainder=0.
    def feed(self,points,now):
        p=checked_landmarks(points)
        distance=lambda a,b:math.hypot(p[a][0]-p[b][0],p[a][1]-p[b][1])
        span=distance(5,17)
        if span<.025: return []
        fingers=[distance(tip,0)>distance(pip,0)*1.12 for tip,pip in ((8,6),(12,10),(16,14),(20,18))]
        pinch=distance(4,8)/span<(.38 if self.kind=='pinch' else .28)
        kind='pinch' if pinch else 'palm' if all(fingers) else 'scroll' if fingers[:2]==[True,True] and not any(fingers[2:]) else 'point' if fingers[0] and not any(fingers[1:]) else 'fist' if not any(fingers) else 'other'
        if kind!=self.kind:
            self.kind=kind;self.since=now;self.scroll_y=None;self.scroll_remainder=0.
            if kind!='pinch': self.clicked=False
            if kind!='fist': self.media_fired=False
        held=now-self.since
        if kind=='palm': return []
        if kind=='point' and held>.045: return [{'action':'move','x':1-p[8][0],'y':p[8][1]}]
        if kind=='pinch' and held>.15 and not self.clicked:
            self.clicked=True;return [{'action':'click'}]
        if kind=='scroll' and held>.2:
            previous=self.scroll_y;self.scroll_y=p[8][1]
            if previous is not None:
                self.scroll_remainder+=(previous-self.scroll_y)*40
                amount=max(-3,min(3,int(self.scroll_remainder)))
                self.scroll_remainder-=amount
                if amount: return [{'action':'scroll','amount':amount}]
        if kind=='fist' and held>.7 and not self.media_fired:
            self.media_fired=True;return [{'action':'media'}]
        return []

class GestureService:
    def __init__(self):
        self.lock=threading.RLock();self.mode='off';self.control=False;self.message='Gesture control is off.'
        self.generation='';self.gate=GestureGate();self.owner=None;self.last=0.;self.seq=-1
        self.stop_event=threading.Event();self.thread=None;self.camera_index=0
        self._frame=None;self._points=();self._preview_at=0.
        self.motion=HandMotion();self._motion_now=0.
    def configure_motion(self,profile):
        if profile not in PROFILES:raise ValueError('Choose Precise, Balanced or Fast.')
        with self.lock:self.motion.profile=profile;self.motion.reset()
    def preview(self):
        with self.lock:
            fresh=time.monotonic()-self._preview_at<1.
            return {**self.status(),'frame':self._frame if fresh else None,'landmarks':self._points if fresh else ()}
    def publish_frame(self,rgb,width,height,generation):
        if type(width) is not int or type(height) is not int or not (0<width<=4096 and 0<height<=2160) or len(rgb)!=width*height*3:
            raise ValueError('Invalid RGB preview frame.')
        with self.lock:
            if self.mode=='pc' and self.generation==generation:
                self._frame=(bytes(rgb),width,height);self._preview_at=time.monotonic()
    def status(self):
        with self.lock:return {'mode':self.mode,'control':self.control,'message':self.message,'generation':self.generation,'gesture':self.gate.kind,'pointer_profile':self.motion.profile}
    def stop(self):
        with self.lock:
            self.stop_event.set();self.mode='off';self.control=False;self.generation=secrets.token_hex(12);self.gate=GestureGate()
            self.message='Gesture control stopped. Camera release requested.'
            self._frame=None;self._points=();self._preview_at=0.
            self.motion.reset()
    def arm(self,mode,control=False,camera_index=0):
        if mode not in ('pc','remote'): raise ValueError('Choose PC webcam or iPad.')
        if type(camera_index) is not int or not 0<=camera_index<=4:raise ValueError('Choose a camera index between 0 and 4.')
        with self.lock:
            if self.thread and self.thread.is_alive(): raise ValueError('Stop the previous camera and wait for it to release before switching.')
            if self.mode!='off': raise ValueError('Stop the current gesture session before switching cameras.')
            from core.eye_control import service as eyes
            if eyes.active:raise ValueError('Stop eye control before starting hand control.')
            if mode=='pc':
                from core.camera_lease import claim
                claim('hands')
            self.stop_event=threading.Event();self.mode=mode;self.control=bool(control);self.owner=None
            self.camera_index=camera_index
            self.generation=secrets.token_hex(12);self.gate=GestureGate();self.last=0.;self.seq=-1
            self._frame=None;self._points=();self._preview_at=0.
            self.motion.reset()
            self.message='Preview only; Windows input is disabled.' if not control else 'Windows input enabled. Open palm pauses; Stop disables everything.'
            if mode=='pc':
                self.thread=threading.Thread(target=self._camera,daemon=True,name='local-hand-camera');self.thread.start()
            if control:
                from core.input_stop import register_stop
                if not register_stop(self.stop):
                    self.stop();raise ValueError('Ctrl+Alt+G is already in use. Close the other control session before enabling gesture input.')
    def set_control(self,enabled):
        """Change input permission without restarting a working camera."""
        with self.lock:
            if enabled and self.mode=='off':raise ValueError('Start the gesture camera first.')
            if enabled:
                from core.input_stop import register_stop
                if not register_stop(self.stop):raise ValueError('Ctrl+Alt+G is in use. Close the other JARVIS control session first.')
            self.control=bool(enabled);self.gate=GestureGate();self.motion.reset()
            self.message=('Windows input ON. Point with your index finger to move; pinch to click. Open palm pauses.' if enabled else 'Preview only. Turn on Windows pointer control to move the cursor.')
    def feed(self,points,source,generation,seq,actor='pc',now=None):
        now=time.monotonic() if now is None else now
        with self.lock:
            if self.mode!=source or generation!=self.generation: raise ValueError('Gesture session is not armed or has expired.')
            if self.owner and self.owner!=actor and now-self.last<5: raise ValueError('Another paired device owns this gesture session.')
            if self.owner!=actor:self.seq=-1;self.gate=GestureGate();self.motion.reset()
            if type(seq) is not int or seq<=self.seq: raise ValueError('Stale gesture frame.')
            if now-self.last<1/35: return []
            if now-self.last>.6:self.gate=GestureGate();self.motion.reset()
            if points==[]:
                self.gate=GestureGate();self.owner=actor;self.seq=seq;self.last=now
                self._points=();self._preview_at=time.monotonic()
                self.motion.reset()
                return []
            actions=self.gate.feed(points,now)
            self._motion_now=now
            if self.gate.kind!='point':self.motion.reset()
            self._points=tuple(checked_landmarks(points));self._preview_at=time.monotonic()
            self.owner=actor;self.seq=seq;self.last=now
            if self.control:
                try:
                    for action in actions:self._apply(action)
                except Exception as error:
                    self.stop();self.message='Windows input stopped: '+str(error)[:200]
                    raise ValueError(self.message) from error
            return actions
    def _apply(self,event):
        import pyautogui as mouse
        mouse.FAILSAFE=True
        if event['action']=='move':
            position=self.motion.sample(event['x'],event['y'],self._motion_now,mouse.size(),mouse.position())
            if position:mouse.moveTo(*position,duration=0,_pause=False)
        elif event['action']=='click':mouse.click()
        elif event['action']=='scroll':mouse.scroll(event['amount'])
        elif event['action']=='media':mouse.press('playpause')
    def _camera(self):
        camera=None
        with self.lock:
            generation=self.generation;stop_event=self.stop_event;camera_index=self.camera_index
        try:
            # A stop can win the race with this worker starting. The lease
            # still belongs to this worker and must pass through finally.
            with self.lock:
                if self.mode!='pc' or stop_event.is_set():return
            import cv2
            import mediapipe as mp
            model=ROOT/'models/hand_landmarker.task'
            if not model.exists():raise RuntimeError('Hand model is missing. Run Prepare-Local.ps1 to download assets before offline use.')
            options=mp.tasks.vision.HandLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),running_mode=mp.tasks.vision.RunningMode.VIDEO,num_hands=1,min_hand_detection_confidence=.7,min_tracking_confidence=.7)
            from core.camera_capture import open_camera,read_frame,VideoClock
            camera=open_camera(camera_index);clock=VideoClock()
            with mp.tasks.vision.HandLandmarker.create_from_options(options) as detector:
                seq=0
                while not stop_event.is_set():
                    frame=read_frame(camera,stop_event)
                    if frame is None:break
                    rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
                    self.publish_frame(rgb.tobytes(),rgb.shape[1],rgb.shape[0],generation)
                    image=mp.Image(image_format=mp.ImageFormat.SRGB,data=rgb)
                    result=detector.detect_for_video(image,clock.next())
                    with self.lock:
                        # Stop/close may arrive while read/inference is running.
                        # Discard its last result instead of treating it as an error.
                        if stop_event.is_set() or self.mode!='pc' or self.generation!=generation:break
                        points=([[max(0.,min(1.,p.x)),max(0.,min(1.,p.y)),max(-2.,min(2.,p.z))] for p in result.hand_landmarks[0]] if result.hand_landmarks else [])
                        self.feed(points,'pc',generation,seq);seq+=1
                    stop_event.wait(.001)
        except Exception as error:
            with self.lock:
                if not stop_event.is_set() and self.mode=='pc' and self.generation==generation:
                    self.stop();self.message='Gesture camera stopped: '+str(error)[:250]
                    print('[Gestures] '+self.message,flush=True)
        finally:
            if camera is not None:camera.release()
            from core.camera_lease import release
            release('hands')

service=GestureService()
