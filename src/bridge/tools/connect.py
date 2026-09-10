"""connect — wire nodes, break a wire, change input order."""
from typing import Any, Dict, List, Union

from ..connection import call_json


def tool(mode: str = "connect",
         items: Union[Dict[str, Any], List[Dict[str, Any]]] = None,
         src_path: str = None, dst_path: str = None, dst_input_index: int = 0,
         src_output_index: int = 0, path: str = None, input_index: int = 0,
         input_indices: List[int] = None) -> str:
    """Change how nodes feed each other.

    Use it after node_edit made the nodes. A list of wires goes in one undo
    group and one round trip.

    mode:
        "connect"    — src_path feeds dst_path. dst_input_index chooses the
                       input, src_output_index the output. Both count from 0.
        "disconnect" — path loses the wire on input_index.
        "reorder"    — path takes its inputs in the order input_indices.

    items: a list of wires for "connect" and "disconnect", each a dictionary
    with the same keys.

    Returns JSON, one line for each wire, with the paths that Houdini used.
    An input index that the node does not have is reported, not dropped.
    """
    arguments = {"mode": mode, "items": items, "dst_input_index": dst_input_index,
                 "src_output_index": src_output_index, "input_index": input_index}
    arguments.update({key: value for key, value in (
        ("src_path", src_path), ("dst_path", dst_path), ("path", path),
        ("input_indices", input_indices),
    ) if value is not None})
    return call_json("connect", arguments)
