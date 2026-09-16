"""Run code inside the Houdini session."""
import io
import os
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr

import hou


LIMIT = 20_000


def execute_code(code, allow_dangerous=True, file=None, globals=None):
    """Run Python inside Houdini and report what it printed.

    `file` runs a script that Houdini reads from disk, so a script that runs
    again with other values does not travel through the conversation twice.
    `globals` is a dictionary of names that exist before the script runs.
    """
    if file:
        if not os.path.isfile(file):
            raise ValueError(f"There is no file at {file}. Houdini reads this path, so it "
                             f"must exist on the machine that runs Houdini.")
        with open(file, encoding="utf-8") as handle:
            code = handle.read()
    if not code:
        raise ValueError("Give source, the code to run, or file, a path to a script.")

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    namespace = {"hou": hou, **(globals or {})}
    failed = None
    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            exec(code, namespace)
    except Exception as error:
        # The output that came before the error is often the whole answer, so
        # it goes back with the error instead of being lost with it.
        failed = f"{type(error).__name__}: {error}\n{traceback.format_exc()}"
        traceback.print_exc(file=sys.stderr)

    report = {
        "executed": failed is None,
        **_cut("stdout", stdout_capture.getvalue()),
        **_cut("stderr", stderr_capture.getvalue()),
    }
    if file:
        report["file"] = file
    if globals:
        report["globals"] = sorted(globals)
    if failed:
        report["error"] = failed
    return report


def _cut(name, text):
    """Keep the start and the end of a long output.

    A client drops a result that is too large, and then the whole call is lost.
    The middle is what a caller needs least.
    """
    if len(text) <= LIMIT:
        return {name: text}
    half = LIMIT // 2
    removed = len(text) - LIMIT
    return {name: f"{text[:half]}\n\n...[{removed} characters and "
                  f"{text.count(chr(10), half, len(text) - half)} lines removed: print "
                  f"less, or write the result to a file]...\n\n{text[-half:]}",
            f"{name}_characters": len(text)}


def execute_hscript(command):
    """Execute an HScript command and return the output."""
    result = hou.hscript(command)
    return {"stdout": result[0], "stderr": result[1]}


def evaluate_expression(expression, language="hscript"):
    """Evaluate a Houdini expression and return the result."""
    if language == "python":
        result = hou.expressionGlobals()
        val = eval(expression, result)
    else:
        val = hou.hscriptExpression(expression)
    return {"expression": expression, "result": str(val), "language": language}


def get_env_variable(name):
    """Get a Houdini environment variable ($HIP, $JOB, etc.)."""
    val = hou.getenv(name)
    return {"name": name, "value": val}
