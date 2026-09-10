"""scene_file — the .hip file on disk."""
from mcp.types import ToolAnnotations

from ..connection import call_json

ANNOTATIONS = ToolAnnotations(destructiveHint=True)


def tool(mode: str = "info", path: str = None) -> str:
    """Read, save or load the scene file.

    Use "save" before a change that is hard to undo, and use "info" to learn
    whether the session holds work that is not saved.

    mode:
        "info" — the file name, the frame range, the counts, and whether the
                 session has changes that are not saved.
        "save" — save to `path`, or over the open file when `path` is empty.
        "load" — open the .hip file at `path`. Everything in the session goes
                 away, and the undo history with it.

    Returns JSON.
    """
    return call_json("scene_file", {"mode": mode, "path": path}, timeout=300.0)
