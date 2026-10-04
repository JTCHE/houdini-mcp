"""connect — wire nodes, break a wire, change input order."""
from typing import Any, Dict, List, Optional, Union

from mcp.types import ToolAnnotations

from ..connection import call_json

ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                              idempotentHint=True, openWorldHint=False)

PARAMS = {
    "mode": 'One of "connect", "disconnect", "reorder".',
    "items": 'A list of wires for "connect" or "disconnect", each a dictionary with the '
             "keys of one wire. An argument outside items is the default for each one.",
    "src_path": "connect: the node whose output feeds the wire.",
    "dst_path": "connect: the node whose input takes the wire.",
    "dst_input_index": "connect: the input of dst_path, from 0.",
    "src_output_index": "connect: the output of src_path, from 0.",
    "path": "disconnect and reorder: the node whose inputs change.",
    "input_index": "disconnect: the input that loses its wire, from 0.",
    "input_indices": "reorder: the old input indices in their new order, for example [1, 0].",
}


def tool(mode: str = "connect",
         items: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
         src_path: str = None, dst_path: str = None, dst_input_index: int = 0,
         src_output_index: int = 0, path: str = None, input_index: int = 0,
         input_indices: List[int] = None) -> str:
    """Change how nodes feed each other.

    Use it after node_edit made the nodes. A list of wires goes in one undo
    group and one round trip.

    Do not use it to wire a node that you make now: node_edit mode "create"
    takes `input_path` and wires it in the same call. Do not use it to read the
    wires: scene_overview mode "network" lists them.

    mode:
        "connect"    — src_path feeds dst_path. dst_input_index chooses the
                       input, src_output_index the output. Both count from 0.
        "disconnect" — path loses the wire on input_index.
        "reorder"    — path takes its inputs in the order input_indices.

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
