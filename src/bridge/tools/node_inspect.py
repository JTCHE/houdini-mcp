"""node_inspect — everything about one node, or about a list of nodes."""
from typing import Any, List, Union

from ..connection import call_json


def tool(paths: Union[str, List[str]], mode: str = "info", parm: str = None,
         include_all_parms: bool = False, object_name: str = None,
         field_name: str = None, channel: str = None,
         start: float = None, end: float = None) -> str:
    """Read one node, or a list of nodes, without changing anything.

    Use it before you write: to confirm a parameter name, to see whether a
    parameter carries an expression, and to read what a node reports after a
    cook.

    Do not use it to list a network: scene_overview does that.

    paths: one node path, or a list of them. A list keeps going after a node
    that fails, and each result names its path.

    mode:
        "info"            — type, inputs, outputs, flags, changed parameters.
        "parms"           — every parameter, or one parameter when you give
                            `parm`. The result says whether the value comes
                            from an expression.
        "schema"          — the parameter templates: types, ranges, menus.
                            Read this before you write a menu parameter.
        "changed"         — only the parameters that are not at their default.
        "expression"      — the expression on `parm`, and its language.
        "keyframes"       — the keys on `parm`.
        "code"            — the VEX snippet in a wrangle node.
        "cook_chain"      — what this node cooks from, upstream.
        "explain"         — a short account of what the node does here.
        "material"        — the shader parameters of a material node.
        "image"           — the COP node: resolution, planes, data type.
        "channels"        — CHOP channels. `channel`, `start` and `end` read
                            the samples of one channel.
        "simulation"      — the DOP network. `object_name` reads one object,
                            with `field_name` one field of it.
        "render_settings" — the parameters of a ROP node.
        "cache"           — the file cache state of a node.

    Returns JSON. A cook error comes back in the result: an empty geometry with
    no error line means the node cooked and made nothing.
    """
    return call_json("node_inspect", {
        "paths": paths, "mode": mode, "parm": parm,
        "include_all_parms": include_all_parms, "object_name": object_name,
        "field_name": field_name, "channel": channel, "start": start, "end": end,
    })
