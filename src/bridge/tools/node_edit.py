"""node_edit — make, name, move, flag and delete nodes."""
from typing import Any, Dict, List, Optional, Union

from mcp.types import ToolAnnotations

from ..connection import call_json

ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                              idempotentHint=False, openWorldHint=False)

PARAMS = {
    "mode": 'One of "create", "delete", "copy", "move", "rename", "flags", "color", '
            '"layout", "wrangle", "material", "assign_material", "take", '
            '"current_network", "note", "box".',
    "items": "A list of items for a repeated action, each a dictionary with the keys of "
             "one call. An argument outside items is the default for each one.",
    "path": "The node to change. layout: the network. delete: a node, a sticky note or a "
            "network box.",
    "parent_path": "create, wrangle, note: the network that gets the new node.",
    "node_type": 'create: the node type, for example "box" or "attribwrangle".',
    "name": "create, material: the name of the new node. take: the name of a new take.",
    "context": 'create: the network kind, "sop" (default), "cop", "chop", "lop" or '
               '"material_network".',
    "position": "create, move, note: [x, y] on the canvas.",
    "parameters": "create, material: values to set on the new node, by parameter name.",
    "destination_path": "copy, move: the network to put the nodes in.",
    "new_name": "rename: the new name.",
    "display": "flags: the display flag.",
    "render": "flags: the render flag, which is not the display flag.",
    "bypass": "flags: the bypass flag.",
    "color": "color, note, box: [r, g, b] from 0 to 1.",
    "code": "wrangle: the VEX snippet.",
    "material_type": 'material: the shader type, for example "principledshader".',
    "material_path": "assign_material: the material node.",
    "take_name": "take: the take to make current.",
    "input_path": "create: the node that feeds the new node. It saves a connect call and "
                  "places the node under its input.",
    "code_file": "wrangle: read the VEX from this file, so a long snippet travels once.",
    "replace": 'wrangle: edit the snippet in place, a list of {"old": ..., "new": ...}. '
               "Each old must appear exactly once.",
    "paths": "copy: the nodes to copy. layout: place only these nodes. box: the nodes to "
             "put in the box.",
    "suffix": "copy: text added to the name of each copy.",
    "names": "copy: a new name for each source, by source path or name.",
    "text": "note: the text of the note. box: the comment of the box.",
}


def tool(mode: str = "create",
         items: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
         path: str = None, parent_path: str = None, node_type: str = None,
         name: str = None, context: str = None, position: List[float] = None,
         parameters: Dict[str, Any] = None, destination_path: str = None,
         new_name: str = None, display: bool = None, render: bool = None,
         bypass: bool = None, color: List[float] = None, code: str = None,
         material_type: str = None, material_path: str = None,
         take_name: str = None, input_path: str = None,
         code_file: str = None, replace: List[Dict[str, str]] = None,
         paths: List[str] = None, suffix: str = None,
         names: Dict[str, str] = None, text: str = None) -> str:
    """Change the nodes in a network. One item, or a list in one undo group.

    Use it to build a network. Then use parm_set for the values, and connect
    for the wires.

    Do not use it to set parameters: parm_set does that, and it reports a write
    that had no effect.

    mode, and the arguments that each mode reads:
        "create"           — node_type, parent_path, name, position,
                             parameters, input_path. context selects the
                             network kind: "sop" (default), "cop", "chop",
                             "lop", "material_network".
        "delete"           — path, of a node, a sticky note or a network box.
        "copy"             — paths (or path), destination_path, suffix,
                             names. Copies a set of nodes with the wires
                             between them; a wire from outside the set goes to
                             the same node. suffix is added to each name, or
                             names maps a source path or name to a new name.
                             Returns `copies`, each source path with the path
                             of its copy: use that map, never the order of a
                             list. Without destination_path the copies go to
                             the right of the sources.
        "move"             — path with destination_path to put it in another
                             network, or path with position to move it on the
                             canvas.
        "rename"           — path, new_name.
        "flags"            — path, display, render, bypass. The display flag
                             and the render flag are different flags.
        "color"            — path, color as [r, g, b] from 0 to 1.
        "layout"           — path: lay out the children of that network in
                             rows, each node under its inputs. Give `paths` to
                             place only those nodes next to what they connect
                             to. Without it the whole network moves, including
                             the nodes the user placed by hand, and the result
                             says so.
        "wrangle"          — parent_path with code to make a wrangle, or path
                             with code to write into one. code_file reads the
                             code from a file, so a long snippet travels once.
                             replace edits a snippet in place: a list of
                             {"old": ..., "new": ...}, and each `old` must
                             appear exactly once.
        "material"         — path, material_type, name, parameters.
        "assign_material"  — path, material_path.
        "take"             — name to make a take, or take_name to select one.
        "current_network"  — path: what the network editor shows.
        "note"             — parent_path, text, position, color: a sticky
                             note. Without position it goes to the right of
                             the nodes.
        "box"              — paths, text, color: a network box around those
                             nodes, with text as its comment.

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
        ("take_name", take_name), ("input_path", input_path),
        ("code_file", code_file), ("replace", replace), ("paths", paths),
        ("suffix", suffix), ("names", names), ("text", text),
    ) if value is not None})
    return call_json("node_edit", arguments)
