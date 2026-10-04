"""playbar — the current frame, the frame range, and playback."""
from mcp.types import ToolAnnotations

from ..connection import call_json

ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                              idempotentHint=True, openWorldHint=False)

PARAMS = {
    "mode": 'One of "get", "frame", "range", "playback", "play".',
    "frame": "frame: the frame to go to.",
    "start": "range and playback: the first frame.",
    "end": "range and playback: the last frame.",
    "action": 'play: "play", "stop", "next", "previous", "start" or "end".',
}


def tool(mode: str = "get", frame: float = None, start: float = None,
         end: float = None, action: str = None) -> str:
    """Read or set the time of the session.

    Use it before you read geometry that changes over time: a SOP cooks at the
    current frame, so the frame decides what you see.

    Do not use it only to read another frame: geometry_inspect, node_inspect
    and stage_inspect take `frames` and put the playbar back after. A frame
    that you set here stays for the person and for every later call, and
    "range" also changes what a flipbook covers, and a ROP whose range
    follows $FSTART and $FEND.

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
