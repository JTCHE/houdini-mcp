"""What changed in a network between two calls of the agent.

A network that the agent watches is read again at the end of each call that
can change the scene. So the next read lists only what changed between the
calls: the work of the user, not the work of the agent.
"""
import hou

# network path -> the state at the end of the last call.
WATCHED = {}


def _parms(node):
    """The parameters that are not at their default, as their raw text: an
    expression stays an expression."""
    found = {}
    for parm in node.parms():
        try:
            if not parm.isAtDefault():
                found[parm.name()] = parm.rawValue()
        except hou.Error:
            continue
    return found


def _flags(node):
    found = {}
    for name, read in (("display", "isDisplayFlagSet"), ("render", "isRenderFlagSet"),
                       ("bypass", "isBypassed")):
        if hasattr(node, read):
            found[name] = getattr(node, read)()
    return found


def snapshot(network):
    nodes = {}
    for node in network.children():
        nodes[node.sessionId()] = {
            "name": node.name(), "type": node.type().name(),
            "position": [round(value, 2) for value in node.position()],
            "flags": _flags(node),
            # A wire names its source by id, so a rename is not a new wire.
            "inputs": [(wire.inputIndex(), _id(wire.inputItem()), wire.outputIndex())
                       for wire in node.inputConnections()],
            "parms": _parms(node)}
    return {"hip": hou.hipFile.path(), "nodes": nodes}


def _id(item):
    return item.sessionId() if isinstance(item, hou.Node) else item.name()


def _wires(inputs, nodes):
    return [f"{index} <- {nodes[source]['name'] if source in nodes else source}"
            for index, source, _ in inputs] or "none"


def _short(value, most=80):
    text = str(value)
    return text if len(text) <= most else text[:most] + "..."


def _diff(old, new):
    found = {}
    if old["hip"] != new["hip"]:
        found["hip_file"] = f"{old['hip']} -> {new['hip']}"
    before, after = old["nodes"], new["nodes"]
    added = [after[key]["name"] for key in after if key not in before]
    deleted = [before[key]["name"] for key in before if key not in after]
    if added:
        found["added"] = added
    if deleted:
        found["deleted"] = deleted
    for key in after.keys() & before.keys():
        was, now = before[key], after[key]
        name = now["name"]
        if was["name"] != name:
            found.setdefault("renamed", []).append(f"{was['name']} -> {name}")
        if was["position"] != now["position"]:
            found.setdefault("moved", []).append(name)
        for flag, value in now["flags"].items():
            if was["flags"].get(flag) != value:
                found.setdefault("flags", []).append(f"{name}: {flag} {'on' if value else 'off'}")
        if was["inputs"] != now["inputs"]:
            found.setdefault("wires", []).append(
                f"{name}: {_wires(was['inputs'], before)} -> {_wires(now['inputs'], after)}")
        for parm in sorted(was["parms"].keys() | now["parms"].keys()):
            one, two = was["parms"].get(parm), now["parms"].get(parm)
            if one != two:
                found.setdefault("parameters", []).append(
                    f"{name}/{parm}: {_short(one) if one is not None else 'default'} -> "
                    f"{_short(two) if two is not None else 'default'}")
    return found


def changes(path):
    """What changed in the network `path` since the last call of the agent.
    The first call starts to watch it."""
    network = hou.node(path)
    if network is None:
        raise ValueError(f"Node not found: {path}")
    now = snapshot(network)
    old = WATCHED.get(network.path())
    WATCHED[network.path()] = now
    if old is None:
        return {"path": network.path(), "watching": True, "nodes": len(now["nodes"]),
                "note": "From now on, this mode lists what changed here between your calls: "
                        "the work of the user. Call it at the start of each turn."}
    found = _diff(old, now)
    return {"path": network.path(), "changed": bool(found), **found}


def refresh():
    """Read each watched network again, at the end of a call that can change
    the scene, so that the changes of the agent are not reported."""
    for path in list(WATCHED):
        network = hou.node(path)
        if network is None:
            del WATCHED[path]
            continue
        WATCHED[path] = snapshot(network)
