"""console — what Houdini said, and which nodes hold errors."""
from mcp.types import ToolAnnotations

from ..connection import call_json

# A read takes the entries away, so a second call gives other entries.
ANNOTATIONS = ToolAnnotations(readOnlyHint=True, idempotentHint=False,
                              openWorldHint=False)

PARAMS = {
    "limit": "How many log entries come back, the newest ones.",
    "severity": 'Keep one level only: "message", "important", "warning", "error" or "fatal".',
    "source": 'Keep the entries whose source holds this text, for example "Python".',
    "node_errors": "Also report the nodes under root_path that hold an error or a warning. "
                   "False gives the log alone.",
    "root_path": "The network that node_errors walks, for example /obj or /stage.",
    "node_limit": "How many nodes with an error or a warning come back. Errors come first, "
                  "and the report says how many it left out.",
}


def tool(limit: int = 100, severity: str = None, source: str = None,
         node_errors: bool = True, root_path: str = "/obj",
         node_limit: int = 20) -> str:
    """Read the Houdini log and the node errors.

    Use it when something did not do what you expected. A cook error often
    hides behind an empty result: the geometry has no points, and the reason is
    here.

    Each call takes the log entries away, so a call returns only what is new
    since the call before it.

    Returns JSON.
    """
    return call_json("console", {"limit": limit, "severity": severity,
                                 "source": source, "node_errors": node_errors,
                                 "root_path": root_path,
                                 "node_limit": node_limit}, timeout=120.0)
