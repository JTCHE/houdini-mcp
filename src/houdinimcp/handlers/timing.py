"""Time: run work at other frames, and measure how long a cook takes.

Every tool that reads or cooks at a frame other than the current one comes
through here, so no tool leaves the user on a frame that they did not choose.
"""
import time

import hou


def frame_list(frames, default=None):
    """The frames a caller asked for, as a list of numbers.

    Accepts one number, a list of numbers, or [start, end, step] written as
    {"start": s, "end": e, "step": n}. A range with no step uses 1.
    """
    if frames is None:
        return list(default or [])
    if isinstance(frames, (int, float)):
        return [float(frames)]
    if isinstance(frames, dict):
        start = float(frames["start"])
        end = float(frames.get("end", start))
        step = float(frames.get("step", 1)) or 1.0
        count = int(abs(end - start) / abs(step)) + 1
        return [start + step * index for index in range(count)]
    return [float(frame) for frame in frames]


class keep_frame:
    """Put the playbar back where the user had it, whatever happens."""

    def __enter__(self):
        self.frame = hou.frame()
        return self

    def __exit__(self, *error):
        if hou.frame() != self.frame:
            hou.setFrame(self.frame)
        return False


def at_frames(frames, work, default=None):
    """Run `work()` at each frame and return one result for each.

    `work` takes no argument: the caller closes over what it needs. The playbar
    goes back to the frame it was on, so a read never moves the user in time.
    """
    wanted = frame_list(frames, default)
    if not wanted:
        return work()
    results = []
    with keep_frame():
        for frame in wanted:
            hou.setFrame(frame)
            results.append({"frame": frame, "result": work()})
    return {"frames": wanted, "results": results}


def cook_over(nodes, frames, force=True):
    """Cook nodes over a list of frames and report the time of each frame.

    The time for each frame is the number that decides a look: it says whether
    a resolution is usable. It costs nothing to measure, and an agent that does
    not get it writes the same loop in `execute` again and again.
    """
    wanted = frame_list(frames, [hou.frame()])
    per_frame = []
    errors, warnings = [], []
    with keep_frame():
        for frame in wanted:
            hou.setFrame(frame)
            started = time.time()
            for node in nodes:
                node.cook(force=force)
            per_frame.append({"frame": frame, "seconds": round(time.time() - started, 3)})
            for node in nodes:
                errors += [f"{node.path()}: {line}" for line in node.errors()]
                warnings += [f"{node.path()}: {line}" for line in node.warnings()]
    seconds = [entry["seconds"] for entry in per_frame]
    slowest = max(per_frame, key=lambda entry: entry["seconds"])
    return {
        "frames": len(per_frame),
        "total_seconds": round(sum(seconds), 3),
        "mean_seconds": round(sum(seconds) / len(seconds), 3),
        "slowest_frame": slowest["frame"],
        "slowest_seconds": slowest["seconds"],
        "per_frame": per_frame,
        # A cook error gives an empty result and no exception, so it belongs
        # in every answer that cooked something.
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
    }
