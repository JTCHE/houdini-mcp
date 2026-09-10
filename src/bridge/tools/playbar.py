"""playbar — the current frame, the frame range, and playback."""
from ..connection import call_json


def tool(mode: str = "get", frame: float = None, start: float = None,
         end: float = None, action: str = "play") -> str:
    """Read or set the time of the session.

    Use it before you read geometry that changes over time: a SOP cooks at the
    current frame, so the frame decides what you see.

    mode:
        "get"      — the current frame and time.
        "frame"    — go to `frame`.
        "range"    — set the scene frame range to `start` and `end`.
        "playback" — set the playback range inside the scene range.
        "play"     — `action` is "play", "stop", "next", "previous", "start"
                     or "end". Playback needs a GUI.

    Returns JSON.
    """
    return call_json("playbar", {"mode": mode, "frame": frame, "start": start,
                                 "end": end, "action": action})
