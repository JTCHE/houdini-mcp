"""Run code inside the Houdini session."""
import io
import os
import sys
import time
import traceback
from contextlib import redirect_stdout, redirect_stderr

import hou

from .. import protocol, watchdog
from . import parameters

LIMIT = 20_000


class _Live(io.StringIO):
    """Keeps what a script prints, and writes it to a file as it comes, so a
    caller that cannot wait for the answer can read the progress."""

    def __init__(self, path):
        super().__init__()
        self.path, self.flushed = path, 0.0
        try:
            self.file = open(path, "w", encoding="utf-8") if path else None
        except OSError:
            self.file = None

    def write(self, text):
        if self.file:
            self.file.write(text)
            if time.monotonic() - self.flushed > 0.5:
                self.file.flush()
                self.flushed = time.monotonic()
        return super().write(text)

    def close_file(self):
        if self.file:
            self.file.close()


class _Writes:
    """Watch what a script changes.

    A script writes parameters with `hou.Parm.set`, `hou.ParmTuple.set` and
    `hou.OpNode.setParms`, and Houdini reports none of the writes that change
    nothing or change another node. While the script runs, these calls go
    through a wrapper that keeps each write. The checks run when the script
    ends, so a write that a later line of the script makes valid (a toggle
    that enables it) is not reported.

    The creation script of a new node writes its own parameters. Those writes
    are not the script's, so they are not reported.

    The wrapper also counts the nodes and the wires that the script makes, and
    the nodes that get new spare parameters.
    """

    def __enter__(self):
        self.writes = {}
        self.creating = 0
        self.created = self.wired = 0
        self.spare_nodes = {}
        self.saved = (hou.Parm.set, hou.ParmTuple.set, hou.OpNode.setParms,
                      hou.Node.createNode, hou.Node.setInput,
                      hou.OpNode.setParmTemplateGroup, hou.OpNode.addSpareParmTuple)
        (parm_set, tuple_set, set_parms, create_node, set_input, set_group,
         add_spare) = self.saved
        record = self.record

        def watched_create_node(node, *rest, **named):
            if not self.creating:
                self.created += 1
            self.creating += 1
            try:
                return create_node(node, *rest, **named)
            finally:
                self.creating -= 1

        def watched_set_input(node, *rest, **named):
            if not self.creating:
                self.wired += 1
            return set_input(node, *rest, **named)

        def watched_set_group(node, *rest, **named):
            if not self.creating:
                self.spare_nodes[node.path()] = node
            return set_group(node, *rest, **named)

        def watched_add_spare(node, *rest, **named):
            if not self.creating:
                self.spare_nodes[node.path()] = node
            return add_spare(node, *rest, **named)

        def watched_parm_set(parm, value, *rest, **named):
            before = parameters._text(parm)
            target = parameters._referenced(parm)
            result = parm_set(parm, value, *rest, **named)
            record(parm, value, target, before)
            return result

        def watched_tuple_set(parm_tuple, values, *rest, **named):
            befores = [parameters._text(parm) for parm in parm_tuple]
            targets = [parameters._referenced(parm) for parm in parm_tuple]
            result = tuple_set(parm_tuple, values, *rest, **named)
            for parm, value, target, before in zip(parm_tuple, values, targets, befores):
                record(parm, value, target, before)
            return result

        def watched_set_parms(node, values, *rest, **named):
            parms = {name: node.parm(name) for name in values}
            targets = {name: parm and parameters._referenced(parm)
                       for name, parm in parms.items()}
            befores = {name: parm and parameters._text(parm) for name, parm in parms.items()}
            result = set_parms(node, values, *rest, **named)
            for name, parm in parms.items():
                if parm:
                    record(parm, values[name], targets[name], befores[name])
            return result

        hou.Parm.set, hou.ParmTuple.set = watched_parm_set, watched_tuple_set
        hou.OpNode.setParms = watched_set_parms
        hou.Node.createNode, hou.Node.setInput = watched_create_node, watched_set_input
        hou.OpNode.setParmTemplateGroup = watched_set_group
        hou.OpNode.addSpareParmTuple = watched_add_spare
        return self

    def record(self, parm, value, target, before):
        if not self.creating:
            # The last write to each parameter decides.
            self.writes[parm.path()] = (parm, value, target, before)

    def __exit__(self, *error):
        (hou.Parm.set, hou.ParmTuple.set, hou.OpNode.setParms, hou.Node.createNode,
         hou.Node.setInput, hou.OpNode.setParmTemplateGroup,
         hou.OpNode.addSpareParmTuple) = self.saved
        return False

    def notes(self):
        """[(kind, line)] for each write that changed nothing or something else,
        read now that the script has ended."""
        found = []
        for parm, value, target, before in self.writes.values():
            try:
                found += parameters.script_write_notes(parm, value, target, before)
            except Exception:
                continue  # the parameter or its node went away
        return found

    def folded(self):
        """Put the spare parameters that the script added to a wrangle into the
        folder that the Create Parameters button makes. The script appended them
        at the bottom, below the code, where the user does not look."""
        from . import spares
        moved = {}
        for path, node in self.spare_nodes.items():
            try:
                names = spares.fold_spares(node)
            except Exception:
                continue
            if names:
                moved[path] = names
        return moved


# A script that builds a network has a named way that reports each error.
BUILD_NOTE = ("This script made {created} nodes and {wired} wires. Build a network with "
              "one batch of node_edit create, connect and parm_set (mode 'spare' for "
              "wrangle controls): it is one round trip too, each step reports its "
              "errors, and a failed step changes nothing.")

WARNING_LIMIT = 12


def _grouped(notes):
    """The write warnings, short enough to read. A script that copies every
    parameter of a node gives hundreds; past the limit they are grouped by
    kind, with a count and the first names."""
    if len(notes) <= WARNING_LIMIT:
        return [line for _, line in notes]
    kinds = {}
    for kind, line in notes:
        entry = kinds.setdefault(kind, {"count": 0, "parms": [], "example": line})
        entry["count"] += 1
        if len(entry["parms"]) < 5:
            entry["parms"].append(line.split(": ", 1)[0])
    return {"count": len(notes), "by_kind": kinds}


def execute_code(code, allow_dangerous=True, file=None, globals=None, args=None,
                 timeout=None):
    """Run Python inside Houdini and report what it printed.

    `file` runs a script that Houdini reads from disk, so a script that runs
    again with other values does not travel through the conversation twice. It
    runs as it would from a shell: `__file__` is its path, `__name__` is
    "__main__", and `args` are in `sys.argv[1:]`.
    `globals` is a dictionary of names that exist before the script runs.
    `timeout` is the budget in seconds. When it is spent the script stops where
    it is, and the answer says where, so Houdini comes back by itself.
    """
    if file:
        if not os.path.isfile(file):
            raise ValueError(f"There is no file at {file}. Houdini reads this path, so it "
                             f"must exist on the machine that runs Houdini.")
        with open(file, encoding="utf-8") as handle:
            code = handle.read()
    if not code:
        raise ValueError("Give source, the code to run, or file, a path to a script.")

    server = getattr(hou.session, "houdinimcp_server", None)
    stdout_capture = _Live(protocol.output_file(server.port) if server else None)
    stderr_capture = io.StringIO()
    name = file or "<execute>"
    namespace = {"hou": hou, "__name__": "__main__", **(globals or {})}
    if file:
        namespace["__file__"] = file
    argv = sys.argv
    sys.argv = [name] + [str(arg) for arg in args or ()]
    failed = stopped = None
    watchdog.budget(timeout)
    writes = _Writes()
    try:
        with writes, redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            exec(compile(code, name, "exec"), namespace)
    except watchdog.Stopped:
        stopped = watchdog.handled()
        failed = f"Stopped, because {stopped}. Here is where it was:\n{traceback.format_exc()}"
    except Exception as error:
        # The output that came before the error is often the whole answer, so
        # it goes back with the error instead of being lost with it.
        failed = f"{type(error).__name__}: {error}\n{traceback.format_exc()}"
        traceback.print_exc(file=sys.stderr)
    finally:
        sys.argv = argv
        stdout_capture.close_file()

    report = {
        "executed": failed is None,
        **_cut("stdout", stdout_capture.getvalue()),
        **_cut("stderr", stderr_capture.getvalue()),
    }
    if file:
        report["file"] = file
    if globals:
        report["globals"] = sorted(globals)
    notes = writes.notes()
    if notes:
        report["write_warnings"] = _grouped(notes)
    folded = writes.folded()
    if folded:
        report["spare_parameters_moved"] = {
            "nodes": folded,
            "note": "The script put these controls at the bottom of the wrangle. They are now "
                    "in the folder above the code, where Create Parameters puts them. Use "
                    "parm_set mode 'spare' next time: it does this itself."}
    if writes.created and writes.wired:
        report["named_tools"] = BUILD_NOTE.format(created=writes.created, wired=writes.wired)
    if stopped:
        report["stopped"] = (f"{stopped}. What the script changed before it stopped stays "
                             f"in the scene. Give a larger timeout, or background=true, "
                             f"for long work.")
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
