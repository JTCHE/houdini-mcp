"""node_edit — make, name, move, flag and delete nodes."""
from typing import Any, Dict, List, Union

from ..connection import call_json


def tool(mode: str = "create", items: Union[Dict[str, Any], List[Dict[str, Any]]] = None,
         path: str = None, parent_path: str = None, node_type: str = None,
         name: str = None, context: str = None, position: List[float] = None,
         parameters: Dict[str, Any] = None, destination_path: str = None,
         new_name: str = None, display: bool = None, render: bool = None,
         bypass: bool = None, color: List[float] = None, code: str = None,
         material_type: str = None, material_path: str = None,
         take_name: str = None) -> str:
    """Change the nodes in a network. One item, or a list in one undo group.

    Use it to build a network. Then use parm_set for the values, and connect
    for the wires.

    Do not use it to set parameters: parm_set does that, and it reports a write
    that had no effect.

    mode, and the arguments that each mode reads:
        "create"           — node_type, parent_path, name, position,
                             parameters. context selects the network kind:
                             "sop" (default), "cop", "chop", "lop",
                             "material_network".
        "delete"           — path.
        "copy"             — path, destination_path.
        "move"             — path with destination_path to put it in another
                             network, or path with position to move it on the
                             canvas.
        "rename"           — path, new_name.
        "flags"            — path, display, render, bypass. The display flag
                             and the render flag are different flags.
        "color"            — path, color as [r, g, b] from 0 to 1.
        "layout"           — path: tidy the children of that network.
        "wrangle"          — parent_path with code to make a wrangle, or path
                             with code to write into one.
        "material"         — path, material_type, name, parameters.
        "assign_material"  — path, material_path.
        "take"             — name to make a take, or take_name to select one.
        "current_network"  — path: what the network editor shows.

    items: a list of items for a repeated action, each item a dictionary with
    the same keys. An argument given outside `items` is the default for every
    item. Leave `items` empty for one action.

    Returns JSON. Houdini adds a numeric suffix when a name is already used, so
    read the path in the result and use that path from then on. Never look the
    node up again by the name you asked for.
    """
    arguments = {"mode": mode, "items": items}
    arguments.update({key: value for key, value in (
        ("path", path), ("parent_path", parent_path), ("node_type", node_type),
        ("name", name), ("context", context), ("position", position),
        ("parameters", parameters), ("destination_path", destination_path),
        ("new_name", new_name), ("display", display), ("render", render),
        ("bypass", bypass), ("color", color), ("code", code),
        ("material_type", material_type), ("material_path", material_path),
        ("take_name", take_name),
    ) if value is not None})
    return call_json("node_edit", arguments)
