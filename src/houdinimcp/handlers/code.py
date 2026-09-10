"""Run code inside the Houdini session."""
import io
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr

import hou


def execute_code(code, allow_dangerous=True):
    """Executes arbitrary Python code within Houdini."""
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    try:
        namespace = {"hou": hou}
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            exec(code, namespace)

        return {
            "executed": True,
            "stdout": stdout_capture.getvalue(),
            "stderr": stderr_capture.getvalue()
        }
    except Exception as e:
        print("--- Houdini MCP: execute_code Error ---", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        print("--- End Error ---", file=sys.stderr)
        raise Exception(f"Code execution error: {str(e)}")


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
