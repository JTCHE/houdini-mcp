"""execute — run code inside the Houdini session."""
from typing import Any, Dict

from mcp.types import ToolAnnotations

from ..connection import call_json

ANNOTATIONS = ToolAnnotations(destructiveHint=True, readOnlyHint=False)


def tool(source: str = None, mode: str = "python", language: str = "hscript",
         name: str = None, file: str = None,
         globals: Dict[str, Any] = None) -> str:
    """Run code in Houdini, with the full `hou` module and no guard.

    Use it for what no other tool covers, and to confirm an API in the live
    session, for example `print(dir(hou.Node))`. The code runs with the rights
    of the Houdini process: it can write files, delete nodes and quit Houdini.

    Prefer a named tool when one exists. A named tool reports what Houdini
    silently refused; code does not. If you write the same script twice, the
    named tool for it is missing: say so in the feedback at the end of the
    session.

    mode:
        "python"     — run `source` as Python. Returns stdout and stderr, and
                       keeps them when the script raises. Print what you want
                       to see: the value of the last line does not come back.
        "hscript"    — run `source` as an HScript command.
        "expression" — evaluate `source` as an expression. `language` is
                       "hscript" or "python".
        "vex_check"  — compile `source` as VEX and report the errors. Nothing
                       runs.
        "env"        — read the Houdini variable `name`, for example "HIP".

    file: a Python file that Houdini reads and runs, instead of `source`. Use it
    for a script that you run again with other values: the text then travels
    once, not once for each run.

    globals: names that exist before the script runs, for example
    {"radius": 2.0}. With `file`, this is how one script covers a set of tests.

    Returns JSON. Long work blocks the session: Houdini answers nothing while a
    heavy loop runs, and a call that takes longer than the timeout makes every
    later call look like a Houdini that stopped. Cook a long frame range in
    parts of a few seconds, or use the cook tool, which does that for you.
    """
    return call_json("execute", {"source": source, "mode": mode,
                                 "language": language, "name": name,
                                 "file": file, "globals": globals}, timeout=300.0)
