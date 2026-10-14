"""render — ROP nodes: make one, start it, and follow the work."""
import json
import os
import subprocess
import sys
from typing import List

from mcp.types import ToolAnnotations

from ..connection import call_json

ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                              idempotentHint=False, openWorldHint=False)

PARAMS = {
    "mode": 'One of "start", "progress", "settings", "create", "watch", "stats", "compare".',
    "path": "start, progress, settings: the ROP node.",
    "frame_range": "start: [start, end] or [start, end, step]. Without it the ROP renders "
                   "its own range.",
    "res_scale": "start: a fraction of the resolution for this render only, 0.5 is half.",
    "wait": "start: return when every image is complete, with its render stats.",
    "reference": "compare: the image to compare `output_path` with.",
    "render_type": 'create: the ROP kind, for example "opengl", "karma", "mantra" or "ifd".',
    "name": "create: the name of the new ROP.",
    "parent_path": "create: the network that gets the ROP.",
    "output_path": "start: the image file for this render only (put $F4 in it for a range). "
                   "watch, stats, compare: the image file.",
}

PROCESS_NAMES = ("husk", "mantra-bin")


def tool(mode: str = "start", path: str = None, frame_range: List[float] = None,
         render_type: str = "opengl", name: str = None, parent_path: str = "/out",
         output_path: str = None, res_scale: float = None, wait: bool = False,
         reference: str = None) -> str:
    """Start a render, read its settings, or watch it run.

    Modes: "start", "progress", "settings", "create", "watch", "stats",
    "compare".

    Use it for a final picture through a ROP node. For a fast look at the
    viewport, use capture instead: it is much quicker.

    mode:
        "start"    — render the ROP at `path`. `frame_range` is [start, end];
                     without it the node renders its own range. `output_path`
                     and `res_scale` hold for this render only: the ROP keeps
                     the output and the size of the user. Use them for test
                     renders. `wait=true` returns when every image is
                     complete (husk ended; up to about 28 minutes), with the
                     render stats of the last one. Without wait, husk can go
                     on after the call.
        "progress" — what the ROP reports about the render.
        "settings" — the output file, the camera, the resolution and the
                     range of the ROP; the render delegate that really runs
                     (`engine` cpu or xpu, and `engine_from`: the ROP
                     renderer, else husk:default_delegate on the render
                     settings prim); a warning when a Karma settings node
                     says another engine; and the changed Karma settings,
                     split into the ones that engine reads and the ones it
                     ignores, with the reason. Karma XPU shows the CPU
                     Quality controls and ignores them; its Limits tab
                     counts. parm_set and execute warn on a write that the
                     engine of the node ignores.
        "create"   — make a ROP of `render_type` ("opengl", "karma", "mantra",
                     "ifd", …) named `name` under `parent_path`.
        "watch"    — count the husk and mantra processes on this machine, and
                     say whether the file at `output_path` is there and how big
                     it is. This mode does not need Houdini, so it also works
                     while Houdini is busy with the render.
        "stats"    — what husk wrote into the image at `output_path`
                     (husk:render_stats): render time, the engine that really
                     ran, each XPU device with its share of the samples,
                     shader compiles, peak memory, the AOVs. A GPU at 0 %
                     with compiles in progress is not a slow GPU.
        "compare"  — the mean and the largest absolute difference of each AOV
                     of `output_path` against `reference`, to tune samples
                     against a clean render.

    Returns JSON. A render that writes no file, with no process running, has
    failed: read the node with cook to see the error.
    """
    if mode == "watch":
        return json.dumps(_watch(output_path), separators=(",", ":"))
    return call_json("render", {"mode": mode, "path": path,
                                "frame_range": frame_range,
                                "render_type": render_type, "name": name,
                                "parent_path": parent_path, "output_path": output_path,
                                "res_scale": res_scale, "wait": wait,
                                "reference": reference}, timeout=1800.0)


def _watch(output_path):
    processes = _render_processes()
    report = {"rendering": bool(processes), "process_count": len(processes),
              "processes": processes}
    if output_path is not None:
        there = os.path.exists(output_path)
        report["output_file"] = {"exists": there}
        if there:
            report["output_file"]["size_bytes"] = os.path.getsize(output_path)
    return report


def _render_processes():
    """The husk and mantra processes of this machine, from the OS."""
    windows = sys.platform == "win32"
    # tasklist /V also reads every window title, which takes tens of seconds on
    # a busy machine. The short form is enough to count the renders.
    command = ["tasklist", "/FO", "CSV"] if windows else ["ps", "aux"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)

    processes = []
    for line in result.stdout.splitlines()[1:]:
        for name in PROCESS_NAMES:
            if name not in line.lower():
                continue
            if windows:
                parts = line.strip('"').split('","')
                processes.append({"name": parts[0] if parts else name,
                                  "pid": parts[1] if len(parts) > 1 else "?",
                                  "memory": parts[4] if len(parts) > 4 else "?"})
            else:
                columns = line.split(None, 10)
                processes.append({"name": name,
                                  "pid": columns[1] if len(columns) > 1 else "?",
                                  "cpu_time": columns[9] if len(columns) > 9 else "?",
                                  "command": columns[10] if len(columns) > 10 else line.strip()})
    return processes
