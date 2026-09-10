"""cook — make Houdini compute, write caches, step simulations."""
from typing import List, Union

from ..connection import call_json


def tool(paths: Union[str, List[str]], mode: str = "cook",
         frame_range: List[float] = None, num_steps: int = 1) -> str:
    """Force work to happen, and report what the work said.

    Use it when a node is dirty and you want its errors now, or to write a
    cache to disk before a render.

    Do not use it to read the result: geometry_inspect does that, and it cooks
    the node as well.

    paths: one node path, or a list of them.

    mode:
        "cook"        — cook the node now, and return its errors and warnings.
        "cache_write" — write the file cache of the node. frame_range is
                        [start, end]; without it the node writes its own range.
        "cache_clear" — remove the cached files of the node.
        "sim_step"    — step a DOP network num_steps frames.
        "sim_reset"   — put a DOP network back to its start frame.

    Returns JSON. A cook can take minutes: this call waits, and a timeout
    message does not mean the cook stopped.
    """
    return call_json("cook", {"paths": paths, "mode": mode,
                              "frame_range": frame_range, "num_steps": num_steps},
                     timeout=600.0)
