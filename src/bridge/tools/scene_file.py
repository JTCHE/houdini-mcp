"""scene_file — the .hip file on disk."""
from typing import List

from mcp.types import ToolAnnotations

from ..connection import call_json

# load drops the session and its undo history.
ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                              idempotentHint=False, openWorldHint=False)

PARAMS = {
    "mode": 'One of "info", "save", "load", "undo", "redo", "merge", "list_file".',
    "path": "save: the file to write; empty saves over the open file. load: the .hip "
            "file to open. merge, list_file: the other .hip file.",
    "nodes": "merge: the node paths to bring from the other file. list_file: the "
             "networks to list.",
    "count": "undo and redo: how many steps.",
}


def tool(mode: str = "info", path: str = None, count: int = 1,
         nodes: List[str] = None) -> str:
    """Read, save or load the scene file, or step its undo history.

    Use "save" before a change that is hard to undo, and use "info" to learn
    whether the session holds work that is not saved.

    mode:
        "info" — the file name, the frame range, the counts, and whether the
                 session has changes that are not saved.
        "save" — save to `path`, or over the open file when `path` is empty.
        "load" — open the .hip file at `path`. Everything in the session goes
                 away, and the undo history with it.
        "undo" — undo `count` steps. Each call of a tool that changes the
                 scene is one step. A batch is one step, except a batch with a
                 step that waits (capture, render): there each step is one.
                 Returns the labels it undid and the next ones.
        "redo" — redo `count` steps.
        "merge" — bring `nodes` from the .hip file at `path`, each with all
                 its children and the wires inside. A name in use is
                 renamed: read `made` for the new paths. One undo step.
        "list_file" — the nodes of the .hip file at `path` (type, inputs,
                 child count), at the top or in the networks of `nodes`. A
                 separate hython reads the file, so this session loads
                 nothing. It takes some seconds.

    Returns JSON.
    """
    return call_json("scene_file", {"mode": mode, "path": path, "count": count,
                                    "nodes": nodes}, timeout=900.0)
