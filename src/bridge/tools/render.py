"""render — ROP nodes: make one, start it, and follow the work."""
import json
import os
import subprocess
import sys
from typing import List

from ..connection import call_json

PROCESS_NAMES = ("husk", "mantra-bin")


def tool(mode: str = "start", path: str = None, frame_range: List[float] = None,
         render_type: str = "opengl", name: str = None, parent_path: str = "/out",
         output_path: str = None) -> str:
    """Start a render, read its settings, or watch it run.

    Use it for a final picture through a ROP node. For a fast look at the
    viewport, use capture instead: it is much quicker.

    mode:
        "start"    — render the ROP at `path`. `frame_range` is [start, end];
                     without it the node renders its own range. A render can
                     take a long time.
        "progress" — what the ROP reports about the render.
        "settings" — the output file, the camera, the resolution and the
                     renderer of the ROP.
        "create"   — make a ROP of `render_type` ("opengl", "karma", "mantra",
                     "ifd", …) named `name` under `parent_path`.
        "watch"    — count the husk and mantra processes on this machine, and
                     say whether the file at `output_path` is there and how big
                     it is. This mode does not need Houdini, so it also works
                     while Houdini is busy with the render.

    Returns JSON. A render that writes no file, with no process running, has
    failed: read the node with cook to see the error.
    """
    if mode == "watch":
        return json.dumps(_watch(output_path), indent=2)
    return call_json("render", {"mode": mode, "path": path,
                                "frame_range": frame_range,
                                "render_type": render_type, "name": name,
                                "parent_path": parent_path}, timeout=1800.0)


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
