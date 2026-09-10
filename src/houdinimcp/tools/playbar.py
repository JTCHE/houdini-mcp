"""The current frame, the frame range and the playbar."""
from . import unknown_mode
from ..handlers import animation, scene

MUTATES = True

MODES = ("get", "frame", "range", "playback", "play")


def run(mode="get", frame=None, start=None, end=None, action="play"):
    if mode == "get":
        return animation.get_frame()
    if mode == "frame":
        return scene.set_frame(frame)
    if mode == "range":
        return animation.set_frame_range(start, end)
    if mode == "playback":
        return animation.set_playback_range(start, end)
    if mode == "play":
        return animation.playbar_control(action)
    raise unknown_mode(mode, MODES)
