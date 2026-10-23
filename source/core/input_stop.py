"""A single Windows emergency hotkey, without a keyboard recording hook."""
import ctypes,sys,threading
_thread=None;_callback=None;_registered=False
def register_stop(callback):
    global _thread,_callback
    _callback=callback
    if sys.platform!='win32':return False
    if _thread and _thread.is_alive():return _registered
    ready=threading.Event()
    def listen():
        global _registered
        from ctypes.wintypes import MSG
        user=ctypes.windll.user32
        _registered=bool(user.RegisterHotKey(None,0x4a51,0x0003|0x4000,ord('G')));ready.set()
        if not _registered:return
        try:
            msg=MSG()
            while user.GetMessageW(ctypes.byref(msg),None,0,0)>0:
                if msg.message==0x0312 and _callback:_callback()
        finally:
            user.UnregisterHotKey(None,0x4a51);_registered=False
    _thread=threading.Thread(target=listen,daemon=True,name='jarvis-emergency-hotkey');_thread.start()
    ready.wait(1);return _registered
