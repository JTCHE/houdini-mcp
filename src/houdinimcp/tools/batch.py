"""Run several tool calls in one round trip and one undo group."""
import inspect

MUTATES = True


def run(operations):
    """operations: [{"tool": "node_edit", "params": {...}}, ...]

    The list stops at the first failure, because a later step usually needs the
    node that an earlier step made. The result says how far it came. A step
    that waits in the event loop (see server._step) makes the batch wait.
    """
    from . import dispatch

    results = []
    for index, operation in enumerate(operations):
        tool = operation.get("tool") or operation.get("type")
        try:
            result = dispatch(tool, operation.get("params", {}))
            if inspect.isgenerator(result):
                result = yield from result
            results.append({"tool": tool, "result": result})
        except Exception as error:
            return {"count": len(results), "results": results, "stopped_at": index,
                    "error": f"{tool}: {type(error).__name__}: {error}"}
    return {"count": len(results), "results": results}
