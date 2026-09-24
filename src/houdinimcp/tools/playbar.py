"""The current frame, the frame range and the playbar."""
from . import unknown_mode
from ..handlers import animation, scene

MUTATES = True

# The arguments that each mode reads. Any other argument is refused: a call
# with no mode reads the frame, and a frame it was given must not pass for a
# frame it set.
READS = {"get": (), "frame": ("frame",), "range": ("start", "end"),
         "playback": ("start", "end"), "play": ("action",)}


def run(mode="get", frame=None, start=None, end=None, action=None):
    if mode not in READS:
        raise unknown_mode(mode, READS)
    given = {name for name, value in (("frame", frame), ("start", start), ("end", end),
                                      ("action", action)) if value is not None}
    ignored = sorted(given - set(READS[mode]))
    if ignored:
        users = sorted(other for other, names in READS.items() if set(ignored) & set(names))
        raise ValueError(f"mode '{mode}' does not read {', '.join(ignored)}, so the call "
                         f"would change nothing. Modes that read it: {', '.join(users)}.")
    if mode == "get":
        return animation.get_frame()
    if mode == "frame":
        if frame is None:
            raise ValueError("mode 'frame' needs frame, the frame to go to.")
        return scene.set_frame(frame)
    if mode == "range":
        return animation.set_frame_range(start, end)
    if mode == "playback":
        return animation.set_playback_range(start, end)
    return animation.playbar_control(action or "play")
