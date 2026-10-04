"""PDG/TOPs handlers."""
import hou


def pdg_cook(path):
    """Start cooking a TOP network (non-blocking)."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    node.executeGraph(False, False, False, False)
    return {"cooking": True, "path": node.path()}


def pdg_status(path):
    """Get cook status and work item counts for a TOP network."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    pdg_node = node.getPDGNode()
    if not pdg_node:
        raise ValueError(f"No PDG node for: {path}")
    counts = {"waiting": 0, "cooking": 0, "cooked": 0, "failed": 0}
    for wi in pdg_node.workItems:
        name = _state_name(wi.state)
        if name in counts:
            counts[name] += 1
    counts["total"] = sum(counts.values())
    return {"path": node.path(), **counts}


def pdg_workitems(path, state=None):
    """List work items for a TOP node, optionally filtered by state."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    pdg_node = node.getPDGNode()
    if not pdg_node:
        raise ValueError(f"No PDG node for: {path}")
    items = []
    for wi in pdg_node.workItems:
        wi_state = _state_name(wi.state)
        if state and state.lower() != wi_state:
            continue
        item = {
            "id": wi.id,
            "index": wi.index,
            "state": wi_state,
            "output_files": [f.path for f in wi.outputFiles],
        }
        items.append(item)
    return {"path": node.path(), "count": len(items), "work_items": items}


def pdg_dirty(path, dirty_all=False):
    """Dirty work items on a TOP node for re-cooking."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    pdg_node = node.getPDGNode()
    if not pdg_node:
        raise ValueError(f"No PDG node for: {path}")
    if dirty_all:
        pdg_node.dirtyAllTasks(True)
    else:
        pdg_node.dirty(True)
    return {"dirtied": True, "path": node.path(), "all": dirty_all}


def pdg_cancel(path):
    """Cancel a running PDG cook."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    context = node.getPDGGraphContext()
    if not context:
        raise ValueError(f"No PDG context for: {path}")
    context.cancelCook()
    return {"cancelled": True, "path": node.path()}


def _state_name(state):
    """The short name of a work item state: "cooked", "failed", "cooking",
    "waiting", or the lower-case enum name for the others."""
    import pdg
    names = {pdg.workItemState.CookedSuccess: "cooked",
             pdg.workItemState.CookedFail: "failed",
             pdg.workItemState.Cooking: "cooking",
             pdg.workItemState.Waiting: "waiting"}
    return names.get(state, str(state).rsplit(".", 1)[-1].lower())
