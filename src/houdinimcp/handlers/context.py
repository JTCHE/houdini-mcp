"""Scene context and introspection handlers."""
import hou

from . import match


def wire_source(connection):
    """What feeds one input, by name inside the network.

    `hou.Node.inputs()` gives the node at the far end and hides a dot on the
    way. A script that reads it and deletes "the input" deletes the wrong node.
    So the item that is directly wired comes first, and the far node after it.
    """
    item = connection.inputItem()
    far = connection.inputNode()
    if isinstance(item, hou.NetworkDot):
        return {"dot": item.name(), "from": far.name() if far else None}
    if isinstance(item, hou.SubnetIndirectInput):
        return {"subnet_input": item.number(), "from": far.path() if far else None}
    return {"from": far.name() if far else None}


def _wire_text(name, connection):
    source = wire_source(connection)
    via = f" via {source['dot']}" if "dot" in source else (
        f" via subnet input {source['subnet_input']}" if "subnet_input" in source else "")
    return f"{source['from']}{via} -> {name}[{connection.inputIndex()}]"


def get_network_overview(path="/obj", pattern=None, node_type=None, compact=False):
    """The nodes of one network and the wires between them, by name.

    Names are relative to the network: the parent path once, not on every
    line. `pattern` and `node_type` keep some nodes, and a wire is kept when
    either end is kept. `compact` returns only the wires.
    """
    network = hou.node(path)
    if not network:
        raise ValueError(f"Node not found: {path}")
    kept = [child for child in network.children()
            if match.matches(pattern, child.name())
            and (not node_type or match.matches(node_type, child.type().name()))]
    names = {child.name() for child in kept}
    wires, nodes = [], []
    for child in network.children():
        for connection in child.inputConnections():
            source = connection.inputNode()
            if child.name() in names or (source is not None and source.name() in names):
                wires.append(_wire_text(child.name(), connection))
    if compact:
        return {"path": path, "node_count": len(kept), "wires": wires}
    for child in kept:
        info = {"name": child.name(), "type": child.type().name()}
        inputs = [{"index": connection.inputIndex(), **wire_source(connection)}
                  for connection in child.inputConnections()]
        if inputs:
            info["inputs"] = inputs
        # outputs() follows dots; outputConnections() stops at a dot.
        readers = sorted({reader.name() for reader in child.outputs()})
        if readers:
            info["outputs"] = readers
        flags = [flag for flag, ask in (("display", "isDisplayFlagSet"),
                                        ("render", "isRenderFlagSet"),
                                        ("bypass", "isBypassed"))
                 if getattr(child, ask, lambda: False)()]
        if flags:
            info["flags"] = flags
        nodes.append(info)
    dots = [{"dot": dot.name(), "from": dot.inputItem().name() if dot.inputItem() else None,
             "readers": len(dot.outputConnections())} for dot in network.networkDots()]
    report = {"path": path, "node_count": len(nodes), "nodes": nodes}
    if dots:
        report["dots"] = dots
    return report


def get_cook_chain(path):
    """Get the cook dependency chain for a node (inputs all the way up)."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    chain = []
    visited = set()

    def _walk(n):
        if n.path() in visited:
            return
        visited.add(n.path())
        for inp in n.inputs():
            if inp:
                _walk(inp)
        chain.append({
            "name": n.name(),
            "path": n.path(),
            "type": n.type().name(),
        })

    _walk(node)
    return {"path": path, "chain": chain}


def explain_node(path):
    """Get a human-readable explanation of a node: type, parms, connections."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    node_type = node.type()
    parms = []
    for parm in node.parms():
        if parm.isAtDefault():
            continue
        parms.append({
            "name": parm.name(),
            "label": parm.parmTemplate().label(),
            "value": str(parm.eval()),
        })
    inputs = []
    for connection in node.inputConnections():
        inputs.append({"index": connection.inputIndex(), **wire_source(connection)})
    outputs = [{"path": out.path(), "type": out.type().name()} for out in node.outputs()]
    return {
        "path": node.path(),
        "type": node_type.name(),
        "label": node_type.description(),
        "category": node_type.category().name(),
        "non_default_parms": parms,
        "inputs": inputs,
        "outputs": outputs,
        "comment": node.comment(),
    }


def get_scene_summary():
    """Get a high-level summary of the entire scene."""
    root = hou.node("/")
    all_nodes = root.allSubChildren()
    type_counts = {}
    for n in all_nodes:
        cat = n.type().category().name()
        type_counts[cat] = type_counts.get(cat, 0) + 1
    hip_file = hou.hipFile.name()
    return {
        "file": hip_file,
        "total_nodes": len(all_nodes),
        "category_counts": type_counts,
        "fps": hou.fps(),
        "frame_range": list(hou.playbar.frameRange()),
        "current_frame": hou.intFrame(),
    }


def get_selection():
    """Get the currently selected nodes."""
    selected = hou.selectedNodes()
    nodes = []
    for n in selected:
        nodes.append({
            "name": n.name(),
            "path": n.path(),
            "type": n.type().name(),
        })
    return {"count": len(nodes), "nodes": nodes}


def set_selection(paths):
    """Set the node selection to the given list of paths."""
    nodes = []
    for p in paths:
        n = hou.node(p)
        if not n:
            raise ValueError(f"Node not found: {p}")
        nodes.append(n)
    # Clear current selection
    for n in hou.selectedNodes():
        n.setSelected(False)
    for n in nodes:
        n.setSelected(True)
    return {"selected": [n.path() for n in nodes]}
