"""Avoid opening one physical webcam from two desktop detectors."""
import threading
_lock=threading.Lock();_owner=None
def claim(owner):
    global _owner
    with _lock:
        if _owner is not None:raise ValueError('The camera is in use by '+_owner+'. Stop that camera first.')
        _owner=owner
def release(owner):
    global _owner
    with _lock:
        if _owner==owner:_owner=None
