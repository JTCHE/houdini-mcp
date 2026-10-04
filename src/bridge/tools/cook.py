"""cook — make Houdini compute, over frames, and report what it cost."""
from typing import Any, Dict, List, Union

from mcp.types import ToolAnnotations

from ..connection import call_json

# cache_clear removes files on disk.
ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                              idempotentHint=False, openWorldHint=False)

PARAMS = {
    "paths": "The node to cook, or a list of nodes.",
    "mode": 'One of "cook", "cache_write", "cache_clear", "sim_step", "sim_reset". '
            "The description says what each one does.",
    "frame_range": "[start, end]: every frame between. For cook and cache_write.",
    "frames": 'One frame, a list of frames, or {"start": 1001, "end": 1010, "step": 2}. '
              "For cook. The playbar goes back after.",
    "num_steps": "How many frames sim_step steps the DOP network.",
    "parameters": 'Values to write before the cook, as {"/obj/geo1/pyro": {"divsize": 0.05}}. '
                  "The result says which writes changed nothing.",
    "force": "Cook even when Houdini thinks the node is up to date.",
}


def tool(paths: Union[str, List[str]], mode: str = "cook",
         frame_range: List[float] = None,
         frames: Union[float, List[float], Dict[str, float]] = None,
         num_steps: int = 1, parameters: Dict[str, Dict[str, Any]] = None,
         force: bool = True) -> str:
    """Force work to happen, and report what the work said and what it cost.

    Use it to run a test: write a few parameters, cook a range of frames, and
    read the seconds for each frame. That is one call, and it is the loop that
    every look iteration needs.

    Do not use it to read the result: geometry_inspect does that, and it cooks
    the node as well.

    mode:
        "cook"        — cook the nodes and return the errors, the warnings and
                        the time. `frames` or `frame_range` cooks over more
                        than one frame; the playbar goes back to where it was.
        "cache_write" — write the file cache of the node. frame_range is
                        [start, end]; without it the node writes its own range.
        "cache_clear" — remove the cached files of the node.
        "sim_step"    — step a DOP network num_steps frames.
        "sim_reset"   — clear the cache of a simulation, so that the next cook
                        runs it again. It accepts a DOP network and a solver
                        SOP such as a Pyro, FLIP, Vellum or RBD solver. After
                        you change anything inside a solver, reset it: the node
                        gives its old result back with no error and no warning.
                        On a solver SOP it cooks the sources first, cooks the
                        start frame after the reset, and reports the
                        primitives there. It fails when the result is empty
                        while the sources are not: that simulation stays
                        empty on every frame.

    Returns JSON: the seconds in total, for each frame, and the slowest frame,
    with the errors and the warnings of every node. Each frame also gives the
    point count, the primitive count and the bounds of each SOP: one call
    checks that a result moves or grows over a range. `ok` is false when a
    node failed to cook, and `failed` then names each node upstream of it or
    inside it that holds an error, with the text: the node that broke is
    often another node than the one you cooked. A cook can take minutes:
    the call waits, and a timeout does not stop the cook. Cook a long range in
    parts of a few seconds, so that one call does not block Houdini past the
    timeout.
    """
    return call_json("cook", {"paths": paths, "mode": mode,
                              "frame_range": frame_range, "frames": frames,
                              "num_steps": num_steps, "parameters": parameters,
                              "force": force},
                     timeout=600.0)
