"""batch — several tool calls in one round trip and one undo group."""
import json
from typing import Any, Dict, List

from ..connection import call_json


def tool(operations: List[Dict[str, Any]]) -> str:
    """Run several Houdini tools in one call.

    Use it to build a network: many nodes, their wires and their parameters go
    in one round trip and one undo group, and a person can undo the whole thing
    with one keystroke.

    Do not use it when a later step needs to read what an earlier step made.
    The list runs without you in the middle, so nothing can branch on a result.

    operations: a list. Each item is {"tool": "<tool name>", "params": {...}},
    with the same parameters that the tool takes on its own. Every tool in this
    server can go in the list, except batch itself.

    Returns JSON with one result for each operation. The list stops at the
    first failure, because a later step usually needs the node that an earlier
    step made: the report names the index that failed and the error, and the
    steps before it stay.
    """
    for operation in operations:
        if (operation.get("tool") or operation.get("type")) == "batch":
            return json.dumps({"error": "batch cannot hold batch."})
    return call_json("batch", {"operations": operations}, timeout=600.0)
