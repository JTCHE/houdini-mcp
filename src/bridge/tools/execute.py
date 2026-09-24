"""execute — run code inside the Houdini session."""
import json
import threading
import time
from typing import Any, Dict, List

from mcp.types import ToolAnnotations

from houdinimcp import protocol

from .. import connection
from ..connection import HoudiniError, call_json

ANNOTATIONS = ToolAnnotations(destructiveHint=True, readOnlyHint=False)

# Background jobs of this bridge, by id. A job holds the connection while it
# runs, so Houdini answers the next call only when it ends.
JOBS = {}


def tool(source: str = None, mode: str = "python", language: str = "hscript",
         name: str = None, file: str = None, globals: Dict[str, Any] = None,
         args: List[str] = None, timeout: float = 30.0, background: bool = False,
         job: str = None) -> str:
    """Run code in Houdini, with the full `hou` module and no guard.

    Use it for what no other tool covers, and to confirm an API in the live
    session, for example `print(dir(hou.Node))`. The code runs with the rights
    of the Houdini process: it can write files, delete nodes and quit Houdini.

    Prefer a named tool when one exists. A write in code to a parameter that
    holds an expression, that is disabled or hidden, or whose range clamps the
    value changes nothing, and a write to a channel reference changes another
    node. The answer lists each such write in `write_warnings`; read it. If you
    write the same script twice, the named tool for it is missing: say so in
    the feedback at the end of the session.

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
        "job"        — the state of the background job `job`: running, with
                       what it printed so far, or done, with its result.

    file: a Python file that Houdini reads and runs, instead of `source`. It
    runs as from a shell: `__file__` is its path, `__name__` is "__main__",
    and `args` are in `sys.argv[1:]`. Use it for a script that you run again
    with other values: the text then travels once, not once for each run.

    globals: names that exist before the script runs, for example
    {"radius": 2.0}.

    timeout: the seconds the script may run, 30 by default. Houdini answers
    nothing while a script runs, so a script past its budget stops where it
    is, and the answer says where. What it changed before that stays.

    background: return at once with a job id, and let the script run. Read it
    with mode "job". Use it with a large timeout for long work, such as a
    sweep. Other calls wait until it ends; session action='interrupt' stops it.
    """
    if mode == "job":
        return _job_report(job)
    params = {"source": source, "mode": mode, "language": language, "name": name,
              "file": file, "globals": globals, "args": args,
              "timeout": timeout if mode == "python" else None}
    if background:
        if mode != "python":
            raise HoudiniError("background=true runs Python only. Use mode 'python'.")
        return _start_job(params, timeout)
    return call_json("execute", params, timeout=timeout + 30.0)


def _start_job(params, budget):
    number = f"job-{len(JOBS) + 1}"
    record = {"job": number, "state": "running", "started": time.monotonic(),
              "timeout": budget}
    JOBS[number] = record

    def work():
        try:
            record["result"] = json.loads(call_json("execute", params,
                                                    timeout=budget + 60.0, label=number))
            record["state"] = "done"
        except Exception as error:
            record["error"] = str(error)
            record["state"] = "failed"
        record["seconds"] = round(time.monotonic() - record["started"], 1)

    threading.Thread(target=work, name=number, daemon=True).start()
    # Return when the job holds the connection, so no later call can slip in
    # before it and the job never waits behind another call.
    deadline = time.monotonic() + 10.0
    while record["state"] == "running" and time.monotonic() < deadline:
        live = connection._connection
        if live is not None and live.running and live.running.get("label") == number:
            record["port"] = live.port
            break
        time.sleep(0.05)
    return json.dumps({"job": number, "state": record["state"],
                       "port": record.get("port"), "timeout": budget,
                       "next": f"Read it with execute mode='job' job='{number}'. Other "
                               f"calls wait until it ends; session action='interrupt' "
                               f"stops it."}, indent=2)


def _job_report(job):
    record = JOBS.get(job)
    if record is None:
        raise HoudiniError(f"No job '{job}' in this bridge. Jobs: "
                           f"{', '.join(JOBS) or 'none'}.")
    report = {key: record[key] for key in ("job", "state", "timeout") if key in record}
    if record["state"] == "running":
        report["seconds"] = round(time.monotonic() - record["started"], 1)
        report["printed_so_far"] = _tail(record.get("port"))
        report["next"] = "Read it again later, or stop it with session action='interrupt'."
    else:
        report["seconds"] = record.get("seconds")
        report.update({key: record[key] for key in ("result", "error") if key in record})
    return json.dumps(report, indent=2, default=str)


def _tail(port, most=4000):
    """The end of what the running script has printed. Houdini writes it to a
    file as it goes, on this machine."""
    if not port:
        return None
    try:
        with open(protocol.output_file(port), encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return None
    return text if len(text) <= most else f"...[{len(text) - most} characters]...\n" + text[-most:]
