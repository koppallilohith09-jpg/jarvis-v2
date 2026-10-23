"""Clutched pointer mapping: reacquisition anchors without moving the cursor."""
import math
PROFILES={'Precise':(.85,.035),'Balanced':(1.35,.018),'Fast':(1.8,.009)}
class HandMotion:
    def __init__(self,profile='Balanced'):self.profile=profile;self.reset()
    def reset(self):self.anchor=None;self.last=None;self.output=None;self.at=None
    def sample(self,x,y,now,screen,current):
        width,height=screen
        if self.anchor is None:
            self.anchor=(x,y,float(current[0]),float(current[1]));self.last=(x,y);self.output=(float(current[0]),float(current[1]));self.at=now;return None
        dt=max(.001,min(.1,now-self.at));distance=math.hypot(x-self.last[0],y-self.last[1]);speed=distance/dt
        if distance>.32:self.reset();return self.sample(x,y,now,screen,current)
        gain,tau=PROFILES[self.profile];ax,ay,px,py=self.anchor
        target=(max(5,min(width-5,px+(x-ax)*width*gain)),max(5,min(height-5,py+(y-ay)*height*gain)))
        alpha=1-math.exp(-dt/(tau/(1+speed*2)))
        result=tuple(a+alpha*(b-a) for a,b in zip(self.output,target))
        self.last=(x,y);self.at=now
        if math.hypot(result[0]-self.output[0],result[1]-self.output[1])<.7:return None
        self.output=result;return tuple(round(v) for v in result)
