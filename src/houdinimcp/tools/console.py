"""What Houdini said: the log stream, and the errors on nodes.

The log comes from the session sink that the Log Viewer pane also reads, so a
message that a person can see in Houdini also arrives here. Reading takes the
entries away, so each call returns what is new since the call before it.
"""
import time

import hou

from ..handlers import nodes

MUTATES = False


def run(limit=100, severity=None, source=None, node_errors=True, root_path="/obj"):
    """severity: one of 'message', 'important', 'warning', 'error', 'fatal'."""
    sink = hou.logging.defaultSink(True)
    entries = []
    for entry in sink.stealLogEntries():
        record = {
            "time": time.strftime("%H:%M:%S", time.localtime(entry.time())),
            "source": entry.source(),
            "context": entry.sourceContext(),
            "severity": str(entry.severity()).replace("severityType.", ""),
            "message": entry.message(),
        }
        if source and source.lower() not in (record["source"] or "").lower():
            continue
        if severity and severity.lower() != record["severity"].lower():
            continue
        entries.append(record)

    report = {"count": len(entries), "log": entries[-limit:]}
    if node_errors:
        # A cook error also hides behind an empty geometry result, so read it here.
        report["node_errors"] = nodes.find_error_nodes(root_path)
    return report
