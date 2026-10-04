"""Run several tool calls in one round trip, all or nothing."""
import inspect
import uuid

import hou

MUTATES = False  # run opens the undo groups itself, so that it can roll them back


def run(operations):
    """operations: [{"tool": "node_edit", "params": {...}}, ...]

    The list stops at the first failure, and undoes the steps before it, so a
    failed batch leaves the scene as it was. An item of a step that fails
    counts as a failure of the step. A step that waits in the event loop (see
    server._step) makes the batch wait.
    """
    from . import module_of

    label = f"MCP: batch {uuid.uuid4().hex[:8]}"
    tools = [operation.get("tool") or operation.get("type") for operation in operations]
    if any(inspect.isgeneratorfunction(module_of(tool).run) for tool in tools):
        # A group must not stay open while the event loop runs, so each step
        # gets its own group. They share the label, for the roll back.
        report = yield from _steps(operations, tools, label)
    else:
        with hou.undos.group(label):
            report = yield from _steps(operations, tools, None)
    if "error" in report:
        # The results name nodes that the roll back removed.
        report.pop("results")
        report.pop("count")
        undone = _undo(label)
        report["rolled_back"] = (
            "Nothing changed: the batch undid the steps before the failure."
            if hou.undos.areEnabled() else
            f"Undo is off in this session, so the steps before step {report['stopped_at']} stay.")
        report["undone_groups"] = undone
    else:
        report["check"] = _check(report["results"])
    return report


def _steps(operations, tools, label):
    from . import dispatch

    results = []
    for index, (operation, tool) in enumerate(zip(operations, tools)):
        try:
            result = dispatch(tool, operation.get("params", {}), label)
            if inspect.isgenerator(result):
                result = yield from result
        except Exception as error:
            return {"count": len(results), "results": results, "stopped_at": index,
                    "error": f"{tool}: {type(error).__name__}: {error}"}
        failure = _failure(result)
        if failure:
            report = {"count": len(results), "results": results, "stopped_at": index,
                      "error": f"{tool}: {failure}"}
            if "error" not in result:
                report["failed_result"] = result  # what else the step did
            return report
        results.append({"tool": tool, "result": result})
    return {"count": len(results), "results": results}


def _failure(result):
    """The error of a step that caught its own error, per item or for the whole
    call. A parameter write that did not apply is an error too: a build with a
    wrong parameter name is not the build that was asked for."""
    if not isinstance(result, dict):
        return None
    if "error" in result:
        return result["error"]
    if result.get("applied") is False:
        return f"{result.get('parm')} on {result.get('path')} did not apply: {result.get('reason')}"
    if result.get("not_applied"):
        changes = result.get("parameters") or result.get("changes") or []
        reasons = [change.get("reason") for change in changes
                   if not change.get("applied")]
        return (f"{', '.join(result['not_applied'])} on {result.get('path')} did not apply: "
                f"{'; '.join(filter(None, reasons))}")
    for item in result.get("results") or []:
        failure = _failure(item)
        if failure:
            return failure
    return None


def _undo(label):
    """Undo the groups on top of the stack that carry this label."""
    count = 0
    while hou.undos.undoLabels() and hou.undos.undoLabels()[0] == label:
        hou.undos.performUndo()
        count += 1
    return count


def _paths(value):
    """Every node path in a result."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "path" and isinstance(item, str):
                yield item
            else:
                yield from _paths(item)
    elif isinstance(value, list):
        for item in value:
            yield from _paths(item)


def _check(results):
    """Cook the display node of every SOP network that the batch touched, and
    name the touched nodes that have errors, so the caller needs no second call
    to know if the build works."""
    nodes = {path: hou.node(path) for path in _paths(results)}
    nodes = {path: node for path, node in nodes.items() if node is not None}
    networks, errors = {}, {}
    for node in nodes.values():
        parent = node.parent()
        if parent is not None and parent.childTypeCategory() == hou.sopNodeTypeCategory():
            networks[parent.path()] = parent
    for path, network in networks.items():
        display = network.displayNode()
        if display is None:
            networks[path] = {"display": None}
            continue
        try:
            geometry = display.geometry()
            networks[path] = {"display": display.path(),
                              "points": geometry.intrinsicValue("pointcount"),
                              "prims": geometry.intrinsicValue("primitivecount")}
        except hou.Error as error:
            networks[path] = {"display": display.path(), "cook_error": str(error)}
    for path, node in nodes.items():
        found = node.errors()
        if found:
            errors[path] = list(found)
    return {"networks": networks, "node_errors": errors}
