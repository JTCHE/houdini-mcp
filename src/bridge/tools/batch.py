"""batch — several tool calls in one round trip and one undo group."""
import json
from typing import Any, Dict, List, Union


from ..connection import call, session_line
from .capture import _picture, _paths


def tool(operations: List[Dict[str, Any]]) -> Union[str, list]:
    """Run several Houdini tools in one call.

    Use it to build a network: many nodes, their wires and their parameters go
    in one round trip and one undo group, and a person can undo the whole thing
    with one keystroke.

    Do not use it when a later step needs to read what an earlier step made.
    The list runs without you in the middle, so nothing can branch on a result.

    operations: a list. Each item is {"tool": "<tool name>", "params": {...}},
    with the same parameters that the tool takes on its own. Every tool in this
    server can go in the list, except batch itself.

    Returns JSON with one result for each operation, and the picture of every
    capture step. The list stops at the first failure, because a later step
    usually needs the node that an earlier step made: the report names the
    index that failed and the error, and the steps before it stay.

    A capture step with no `output` writes to a file of its own, so one batch
    can hold several captures.
    """
    for operation in operations:
        if (operation.get("tool") or operation.get("type")) == "batch":
            return json.dumps({"error": "batch cannot hold batch."})
    report = call("batch", {"operations": operations}, timeout=600.0)
    pictures = []
    for step in report.get("results", []):
        if step.get("tool") != "capture":
            continue
        result = step.get("result") or {}
        for path in _paths(result):
            picture = _picture(path, result)
            if picture is not None:
                pictures.append(picture)
    report["_session"] = session_line()
    return pictures + [json.dumps(report, indent=2, default=str)]
