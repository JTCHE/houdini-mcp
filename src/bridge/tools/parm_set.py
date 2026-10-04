"""parm_set — write parameters, press buttons, write expressions and keyframes."""
from typing import Any, Dict, List, Optional, Union

from mcp.types import ToolAnnotations

from ..connection import call_json

# A write replaces the value that was there. One undo takes it back.
ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                              idempotentHint=False, openWorldHint=False)

PARAMS = {
    "mode": 'One of "value", "press", "expression", "keyframe", "keyframes", '
            '"delete_keyframe", "revert", "lock", "link", "spare", "render_settings", '
            '"chop_export", "snapshot", "restore", "diff".',
    "items": "A list of writes, each a dictionary with the keys of one call. An argument "
             "outside items is the default for each one.",
    "path": "The node that holds the parameter.",
    "parm": 'The parameter name, for example "tx" or "divsize".',
    "value": "value, keyframe: the value to write. A menu takes its token.",
    "parameters": "value: several names and values in one write, as a dictionary. spare: "
                  "the list of controls to add.",
    "expression": "expression: the expression text.",
    "language": 'expression: "hscript" or "python".',
    "frame": "keyframe, delete_keyframe: the frame of the key.",
    "keyframes": "keyframes: a list of {frame, value}.",
    "locked": "lock: true locks the parameter, false unlocks it.",
    "src_path": "link: the node to follow.",
    "src_parm": "link: the parameter to follow.",
    "name": "spare: the name of one control. snapshot, restore, diff: the record on disk.",
    "label": "spare: the label of one control.",
    "parm_type": 'spare: the type of one control, for example "float" or "toggle".',
    "default": "spare: the default of one control.",
    "settings": "render_settings: the ROP parameters to write, by name.",
    "chop_path": "chop_export: the CHOP node.",
    "channel_name": "chop_export: the channel that drives the parameter.",
    "follow_reference": "Write the node at the other end of a channel reference. Without it, "
                        "a write through a reference is refused.",
    "paths": 'snapshot: the nodes to save; "/obj/geo1/*" names every node in a network. '
             "restore: put back only these nodes.",
}


def tool(mode: str = "value",
         items: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
         path: str = None, parm: str = None, value: Any = None,
         parameters: Union[Dict[str, Any], List[Dict[str, Any]]] = None,
         expression: str = None,
         language: str = "hscript", frame: float = None,
         keyframes: List[Dict[str, Any]] = None, locked: bool = None,
         src_path: str = None, src_parm: str = None, name: str = None,
         label: str = None, parm_type: str = None, default: Any = None,
         settings: Dict[str, Any] = None, chop_path: str = None,
         channel_name: str = None, follow_reference: bool = False,
         paths: List[str] = None) -> str:
    """Write parameter values, or press a button. One write, or a list in one
    undo group.

    Use it after node_inspect has confirmed the parameter name and the type.

    A write can be accepted and change nothing, and Houdini says nothing. This
    tool looks for all six causes and names the one it found:
      - the parameter carries an expression, which still decides the value;
      - the parameter is animated, so the value became a new key;
      - the parameter is locked;
      - another parameter disables or hides it, so the cook does not read it;
      - a strict range clamped the value;
      - the parameter reads another node through a channel reference, so the
        write would change that other node. It is refused; give
        `follow_reference=true` to write the node at the other end.
    Read `warnings` and `not_applied` in the result before you report success.

    mode, and the arguments that each mode reads:
        "value"           — path, parm, value. Or path and parameters, a
                            dictionary of several names and values. A menu
                            takes its token, for example "custom". A
                            bit-field menu takes a token or a list of them.
        "press"           — path, parm: press a button, for example Save to
                            Disk on a File Cache, Reload on a File SOP, or
                            Resimulate on a solver. The result holds the errors
                            and the warnings of the node after the press,
                            because work that a button starts fails later and
                            in silence.
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
        "spare"           — path, parameters: a list of controls to add, each
                            {name, label, type, default, min, max, strict,
                            help, value, expression, items}. type is "float",
                            "int", "vector", "toggle", "string", "menu" (with
                            items), "ramp" or "color_ramp" (default: a list of
                            [position, value]). One control can also come as
                            name, label, parm_type, default, expression.
                            On a wrangle it first does what the Create
                            Parameters button does, a parameter for each ch()
                            call, and puts every control in that folder above
                            the code. Use it instead of numbers typed into VEX:
                            the user tunes these. A control that exists is
                            replaced in place, so a second call is safe.
        "render_settings" — path, settings for a ROP node.
        "chop_export"     — chop_path, channel_name, path, parm.
        "snapshot"        — name, paths: save every parameter of these nodes,
                            with expressions, keys and the bypass flag, to the
                            record `name` on disk. "/obj/geo1/*" names every
                            node in a network. It overwrites a record of the
                            same name.
        "restore"         — name: put the record back, and list what changed.
                            `paths` limits it to some of the nodes.
        "diff"            — name: list how the scene differs from the record.
                            Changes nothing.
                            In a sweep, restore before each variant, not once
                            at the end: a variant that does not name a
                            parameter keeps the value of the one before.

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
        ("follow_reference", follow_reference or None), ("paths", paths),
    ) if given is not None})
    return call_json("parm_set", arguments)
