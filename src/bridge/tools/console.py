"""console — what Houdini said, and which nodes hold errors."""
from ..connection import call_json


def tool(limit: int = 100, severity: str = None, source: str = None,
         node_errors: bool = True, root_path: str = "/obj") -> str:
    """Read the Houdini log and the node errors.

    Use it when something did not do what you expected. A cook error often
    hides behind an empty result: the geometry has no points, and the reason is
    here.

    Each call takes the log entries away, so a call returns only what is new
    since the call before it.

    limit: how many log entries come back, the newest ones.
    severity: keep one level only: "message", "important", "warning", "error"
              or "fatal".
    source: keep the entries whose source holds this text, for example
            "Python".
    node_errors: also walk the nodes under `root_path` and report the ones with
                 an error or a warning. Set it to False for the log alone.

    Returns JSON.
    """
    return call_json("console", {"limit": limit, "severity": severity,
                                 "source": source, "node_errors": node_errors,
                                 "root_path": root_path}, timeout=120.0)
