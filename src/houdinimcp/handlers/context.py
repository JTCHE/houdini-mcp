"""Scene context and introspection handlers."""
import hou


def get_network_overview(path="/obj"):
    """Get an overview of all nodes in a network with their connections."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    children = node.children()
    nodes = []
    for child in children:
        info = {
            "name": child.name(),
            "path": child.path(),
            "type": child.type().name(),
            "inputs": [inp.path() for inp in child.inputs() if inp],
            "outputs": [conn.outputNode().path() for conn in child.outputConnections()],
        }
        nodes.append(info)
    return {"path": path, "node_count": len(nodes), "nodes": nodes}


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
    for i, inp in enumerate(node.inputs()):
        if inp:
            inputs.append({"index": i, "path": inp.path(), "type": inp.type().name()})
    outputs = []
    for conn in node.outputConnections():
        out = conn.outputNode()
        outputs.append({"path": out.path(), "type": out.type().name(), "input_index": conn.inputIndex()})
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
