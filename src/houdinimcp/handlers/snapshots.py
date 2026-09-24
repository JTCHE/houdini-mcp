"""Save the parameters of a set of nodes, compare with them, and put them back.

A look is found by a sweep: change a few parameters, cook, look, change them
again. A value that one test leaves behind changes every later test, and a
scene that nobody recorded cannot be put back. A record lives on disk, so the
agent that cleans up does not have to be the agent that made the change.
"""
import json
import os
import re
import time

import hou

from .. import protocol

DIRECTORY = os.path.join(protocol.data_dir(), "snapshots")
# Templates that hold no value: they only lay out the pane.
_LAYOUT = {"Folder", "Label", "Separator", "Button", "FolderSet"}


def _file(name):
    if not name or not re.fullmatch(r"[\w.-]+", name):
        raise ValueError(f"A record needs a name of letters, digits, '_', '-' or '.', "
                         f"not {name!r}.")
    return os.path.join(DIRECTORY, f"{name}.json")


def _nodes(paths):
    """The nodes that `paths` names. A path that ends in "/*" names every
    child of that network."""
    found = []
    for path in paths:
        parent, _, pattern = path.rpartition("/")
        if "*" in pattern:
            network = hou.node(parent or "/")
            if network is None:
                raise ValueError(f"Node not found: {parent}")
            found += list(network.glob(pattern))
        else:
            node = hou.node(path)
            if node is None:
                raise ValueError(f"Node not found: {path}")
            found.append(node)
    return found


def _saved(parm):
    """What a parameter holds, in a form that can be put back exactly, or None
    for a parameter that holds no value.

    An expression is kept as its text, never as its value at this frame: a
    value would turn a live link into a frozen number.
    """
    template = parm.parmTemplate()
    kind = template.type().name()
    if kind in _LAYOUT and not parm.isMultiParmParent():
        return None
    if kind == "Ramp":
        ramp = parm.evalAsRamp()
        return {"ramp": {"basis": [basis.name() for basis in ramp.basis()],
                         "keys": list(ramp.keys()),
                         # JSON gives a colour back as a list, so keep it as one.
                         "values": [list(value) if isinstance(value, tuple) else value
                                    for value in ramp.values()]}}
    parent = parm.parentMultiParm()
    if parent is not None and parent.parmTemplate().type() == hou.parmTemplateType.Ramp:
        return None   # the ramp entry holds its keys
    keys = parm.keyframes()
    # An expression is one key whose value Houdini does not use.
    if len(keys) == 1 and keys[0].isExpressionSet() and not keys[0].isValueUsed():
        return {"expression": parm.expression(), "language": parm.expressionLanguage().name()}
    if keys:
        return {"keys": [key.asJSON() for key in keys]}
    if template.type() == hou.parmTemplateType.String:
        return {"value": parm.unexpandedString()}
    value = parm.eval()
    return {"value": value} if isinstance(value, (int, float, str)) else None


def _put(parm, saved):
    """Put a saved state back on a parameter."""
    # setExpression on a parameter that has keys leaves two keys, and then
    # `expression()` fails. Start from no keys.
    parm.deleteAllKeyframes()
    if "ramp" in saved:
        ramp = saved["ramp"]
        values = [tuple(value) if isinstance(value, list) else value
                  for value in ramp["values"]]
        parm.set(hou.Ramp([getattr(hou.rampBasis, name) for name in ramp["basis"]],
                          ramp["keys"], values))
    elif "expression" in saved:
        parm.setExpression(saved["expression"],
                           getattr(hou.exprLanguage, saved["language"]))
    elif "keys" in saved:
        for data in saved["keys"]:
            key = hou.Keyframe()
            key.fromJSON(data)
            parm.setKeyframe(key)
    else:
        parm.set(saved["value"])


def _state(node):
    """Every value of a node that a record keeps, in the order of the pane, so
    a multiparm count comes before the parameters that it makes."""
    parms = {}
    for parm in node.parms():
        saved = _saved(parm)
        if saved is not None:
            parms[parm.name()] = saved
    return {"bypass": getattr(node, "isBypassed", lambda: None)(), "parms": parms}


def snapshot(name, paths):
    """Write the parameters of the nodes at `paths` to the record `name`."""
    nodes = _nodes(paths)
    record = {"name": name, "hip": hou.hipFile.path(), "time": time.strftime("%Y-%m-%d %H:%M:%S"),
              "nodes": {node.path(): _state(node) for node in nodes}}
    os.makedirs(DIRECTORY, exist_ok=True)
    with open(_file(name), "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=1)
    return {"name": name, "file": _file(name), "nodes": len(nodes),
            "parameters": sum(len(state["parms"]) for state in record["nodes"].values())}


def _load(name):
    try:
        with open(_file(name), encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        names = sorted(entry[:-5] for entry in os.listdir(DIRECTORY)
                       if entry.endswith(".json")) if os.path.isdir(DIRECTORY) else []
        raise ValueError(f"No record '{name}'. Records: {', '.join(names) or 'none'}.")


def _short(saved):
    """One short text for a saved state, for a difference line."""
    if saved is None:
        return None
    if "value" in saved:
        return saved["value"]
    if "expression" in saved:
        return f"expression {saved['expression']}"
    if "keys" in saved:
        return f"{len(saved['keys'])} keys"
    return f"ramp of {len(saved['ramp']['keys'])} keys"


def _differences(record, paths=None, write=False):
    """Compare the scene with a record, and put the record back when `write`."""
    keep = {node.path() for node in _nodes(paths)} if paths else None
    changes, missing = [], []
    for path, state in record["nodes"].items():
        if keep is not None and path not in keep:
            continue
        node = hou.node(path)
        if node is None:
            missing.append(path)
            continue
        bypass = getattr(node, "isBypassed", lambda: None)()
        if state["bypass"] is not None and bypass != state["bypass"]:
            changes.append({"path": path, "parm": "(bypass)", "now": bypass,
                            "record": state["bypass"]})
            if write:
                node.bypass(state["bypass"])
        for name, saved in state["parms"].items():
            parm = node.parm(name)
            if parm is None:
                missing.append(f"{path}/{name}")
                continue
            now = _saved(parm)
            if now == saved:
                continue
            change = {"path": path, "parm": name, "now": _short(now), "record": _short(saved)}
            if write:
                try:
                    _put(parm, saved)
                except (hou.Error, TypeError, ValueError) as error:
                    change["error"] = f"{type(error).__name__}: {error}"
            changes.append(change)
    return changes, missing


def restore(name, paths=None):
    """Put the record `name` back, and list what it changed."""
    record = _load(name)
    changes, missing = _differences(record, paths, write=True)
    report = {"name": name, "changed": len(changes), "changes": changes}
    failed = [change for change in changes if "error" in change]
    if failed:
        report["not_restored"] = len(failed)
    if missing:
        report["missing"] = missing
    return report


def diff(name, paths=None):
    """The differences between the scene and the record `name`. Changes nothing."""
    record = _load(name)
    changes, missing = _differences(record, paths)
    report = {"name": name, "recorded": record["time"], "count": len(changes),
              "differences": changes}
    if missing:
        report["missing"] = missing
    return report
