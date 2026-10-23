"""Offline English Kokoro adapter, preserving the user's British voice choice."""
import asyncio
from importlib.util import find_spec
from pathlib import Path
import threading
import os
from .base import Field
from . import audio
from .tts_piper import _split

_lock=threading.Lock()
_engine=None

def model_folder():
    import sys
    root=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent.parent
    choices=[root/'models/kokoro',root.parent/'jarvis-desktop/native/models/kokoro']
    return next((p for p in choices if (p/'kokoro-v1.0.int8.onnx').exists()),choices[0])

class KokoroTTS:
    caps={'audio_out':True}
    def __init__(self,cfg):
        self.voice=str(cfg.get('voice') or 'bm_george')
        if self.voice not in ('bm_george','bm_fable','bm_daniel','bm_lewis'): raise ValueError('Choose an installed Kokoro British voice.')
        self.speed=max(.7,min(1.3,float(cfg.get('speed') or 1)))
        self.last_voice=self.voice
    def _synth(self,text):
        global _engine
        with _lock:
            import numpy as np
            import onnxruntime as ort
            from kokoro_onnx import Kokoro
            folder=model_folder()
            if not (folder/'voices-v1.0.bin').exists(): raise RuntimeError('Kokoro voice assets are missing. Run local setup first; runtime downloads are disabled.')
            if _engine is None:
                ort.disable_telemetry_events()
                opts=ort.SessionOptions();opts.intra_op_num_threads=max(2,min(8,(os.cpu_count() or 4)//4));opts.inter_op_num_threads=1
                session=ort.InferenceSession(str(folder/'kokoro-v1.0.int8.onnx'),sess_options=opts,providers=['CPUExecutionProvider'])
                _engine=Kokoro.from_session(session,str(folder/'voices-v1.0.bin'))
            samples,rate=_engine.create(text,voice=self.voice,speed=self.speed,lang='en-gb')
            return np.clip(samples*32767,-32768,32767).astype('<i2').tobytes(),rate
    async def speak(self,text,voice='',language=''):
        if language and language.split('-')[0].split('_')[0] not in ('en',''):
            raise ValueError('These British Kokoro voices support English; choose an installed local Piper voice for this language.')
        for sentence in _split(text):
            pcm,rate=await asyncio.to_thread(self._synth,sentence)
            for chunk in audio.chunk(audio.resample(pcm,rate,audio.SPEAKER_RATE)): yield chunk
    async def warmup(self,log=None):
        await asyncio.to_thread(self._synth,'Ready.')
        if log:log('SYS: Offline voice is warmed up.')
    def probe(self):
        return ((model_folder()/'voices-v1.0.bin').exists(),'Local Kokoro British voices; no cloud requests.')

PROVIDER={'id':'kokoro','kind':'tts','label':'Kokoro British voice','hint':'Offline George, Fable, Daniel or Lewis',
 'requires':('kokoro_onnx','onnxruntime'),'install':'kokoro-onnx',
 'catalog':({'id':'kokoro','label':'Kokoro British male','local':True,'values':{}},),
 'needs':(Field('voice','Voice',kind='choice',choices=('bm_george','bm_fable','bm_daniel','bm_lewis'),default='bm_george'),
          Field('speed','Speed',kind='number',default=1.0,required=False)),
 'caps':{'audio_out':True},'factory':KokoroTTS}

def available(): return find_spec('kokoro_onnx') is not None and find_spec('onnxruntime') is not None
