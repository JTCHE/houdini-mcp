"""parm_set — write parameters, expressions, keyframes and links."""
from typing import Any, Dict, List, Union

from ..connection import call_json


def tool(mode: str = "value", items: Union[Dict[str, Any], List[Dict[str, Any]]] = None,
         path: str = None, parm: str = None, value: Any = None,
         parameters: Dict[str, Any] = None, expression: str = None,
         language: str = "hscript", frame: float = None,
         keyframes: List[Dict[str, Any]] = None, locked: bool = None,
         src_path: str = None, src_parm: str = None, name: str = None,
         label: str = None, parm_type: str = None, default: Any = None,
         settings: Dict[str, Any] = None, chop_path: str = None,
         channel_name: str = None) -> str:
    """Write parameter values. One write, or a list in one undo group.

    Use it after node_inspect has confirmed the parameter name and the type.

    A write can be accepted and have no effect: a parameter that carries an
    expression keeps the expression, and an animated parameter takes the value
    as a new key. The result says which happened, and lists the writes that did
    not take. Read that list before you report success.

    mode, and the arguments that each mode reads:
        "value"           — path, parm, value. Or path and parameters, a
                            dictionary of several names and values.
        "expression"      — path, parm, expression, language ("hscript" or
                            "python").
        "keyframe"        — path, parm, frame, value.
        "keyframes"       — path, parm, keyframes: a list of {frame, value}.
        "delete_keyframe" — path, parm, frame.
        "revert"          — path, parm: back to the default, and the
                            expression goes away.
        "lock"            — path, parm, locked.
        "link"            — src_path, src_parm, path, parm: the parameter at
                            path follows the one at src_path.
        "spare"           — path, name, label, parm_type ("float", "int",
                            "string", "toggle"), default. Or path and
                            parameters, a list of those dictionaries.
        "render_settings" — path, settings for a ROP node.
        "chop_export"     — chop_path, channel_name, path, parm.

    items: a list of items for several writes, each item a dictionary with the
    same keys. An argument given outside `items` is the default for every item.

    Returns JSON with the value before, the value after, and a reason when the
    write did not take.
    """
    arguments = {"mode": mode, "items": items}
    arguments.update({key: given for key, given in (
        ("path", path), ("parm", parm), ("value", value), ("parameters", parameters),
        ("expression", expression), ("language", language), ("frame", frame),
        ("keyframes", keyframes), ("locked", locked), ("src_path", src_path),
        ("src_parm", src_parm), ("name", name), ("label", label),
        ("parm_type", parm_type), ("default", default), ("settings", settings),
        ("chop_path", chop_path), ("channel_name", channel_name),
    ) if given is not None})
    return call_json("parm_set", arguments)
