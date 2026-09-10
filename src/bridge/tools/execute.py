"""execute — run code inside the Houdini session."""
from mcp.types import ToolAnnotations

from ..connection import call_json

ANNOTATIONS = ToolAnnotations(destructiveHint=True, readOnlyHint=False)


def tool(source: str, mode: str = "python", language: str = "hscript",
         name: str = None) -> str:
    """Run code in Houdini, with the full `hou` module and no guard.

    Use it for what no other tool covers, and to confirm an API in the live
    session, for example `print(dir(hou.Node))`. The code runs with the rights
    of the Houdini process: it can write files, delete nodes and quit Houdini.

    Prefer a named tool when one exists. A named tool reports what Houdini
    silently refused; code does not.

    mode:
        "python"     — run `source` as Python. Returns stdout and stderr.
                       Print what you want to see: the value of the last line
                       does not come back on its own.
        "hscript"    — run `source` as an HScript command.
        "expression" — evaluate `source` as an expression. `language` is
                       "hscript" or "python".
        "vex_check"  — compile `source` as VEX and report the errors. Nothing
                       runs.
        "env"        — read the Houdini variable `name`, for example "HIP".

    Returns JSON. Long work blocks the session: a heavy loop stops Houdini
    from answering until it ends.
    """
    return call_json("execute", {"source": source, "mode": mode,
                                 "language": language, "name": name}, timeout=300.0)
