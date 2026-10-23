"""Bound microphone backlog and handle overflow inside the event-loop callback."""
import asyncio

def put_latest(queue,item):
    if queue is None:return
    if queue.full():
        try:queue.get_nowait()
        except asyncio.QueueEmpty:pass
    try:queue.put_nowait(item)
    except asyncio.QueueFull:pass
