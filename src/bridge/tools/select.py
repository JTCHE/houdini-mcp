"""select — which nodes are selected."""
from typing import List, Union

from mcp.types import ToolAnnotations

from ..connection import call_json

ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                              idempotentHint=True, openWorldHint=False)

PARAMS = {
    "paths": "Leave it out to read the selection. One path or a list of paths replaces it. "
             "An empty list clears it.",
}


def tool(paths: Union[str, List[str]] = None) -> str:
    """Read the node selection, or set it.

    Use it to see what the person works on before you change the scene, and to
    put your own result in front of them when you are done.

    A new selection replaces the one before it. Do not use it to find nodes:
    scene_overview mode "search" does that.

    Returns JSON with the selected paths.
    """
    return call_json("select", {"paths": paths})
