"""batch — several tool calls in one round trip, all or nothing."""
import json
from typing import Any, Dict, List

from mcp.server.mcpserver import Image
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from ..connection import call, session_line
from .capture import _picture, _paths

ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                              idempotentHint=False, openWorldHint=False)

PARAMS = {
    "operations": 'The steps, in order. Each is {"tool": "<tool name>", "params": {...}}, '
                  "with the arguments that the tool takes on its own. Any tool of this "
                  "server except batch.",
}


def tool(operations: List[Dict[str, Any]]) -> list[Image | str]:
    """Run several Houdini tools in one call.

    Use it to build a network: many nodes, their wires and their parameters go
    in one round trip and one undo group, and a person can undo the whole thing
    with one keystroke.

    Do not use it when a later step needs to read what an earlier step made.
    The list runs without you in the middle, so nothing can branch on a result.

    A failed batch changes nothing. Every step is checked before any step
    runs, and a step with a wrong argument stops the batch. A step that fails
    as it runs stops the list, and the steps before it are undone. A step whose
    item failed is a failed step, and so is a parameter write that did not
    apply. The error names the index of the step and its error.

    Returns JSON with one result for each operation, in the order of the
    operations, and the picture of every capture step.

    A batch that works cooks the display node of each SOP network that it
    touched: `check` gives its point and primitive counts, and the touched
    nodes that have errors. Read it before you build on the result.

    A capture step with no `output` writes to a file of its own, so one batch
    can hold several captures.
    """
    from . import validate

    steps = []
    for index, operation in enumerate(operations):
        name = operation.get("tool") or operation.get("type")
        params = {key: value for key, value in (operation.get("params") or {}).items()
                  if value is not None}
        if name == "batch":
            raise ToolError(f"Step {index}: batch cannot hold batch.")
        try:
            validate(name, params)
        except Exception as error:
            raise ToolError(f"Step {index} ({name}) was refused, and no step ran: "
                            f"{error}") from error
        steps.append({"tool": name, "params": params})

    report = call("batch", {"operations": steps}, timeout=600.0)
    if "error" in report:
        report["_session"] = session_line()
        raise ToolError(json.dumps(report, separators=(",", ":"), default=str))
    pictures = []
    for step, result in zip(steps, report.get("results", [])):
        if step["tool"] != "capture" or not isinstance(result, dict):
            continue
        for path in _paths(result):
            picture = _picture(path, result)
            if picture is not None:
                pictures.append(picture)
    report["_session"] = session_line()
    return pictures + [json.dumps(report, separators=(",", ":"), default=str)]
