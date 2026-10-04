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
    show them your result when you are done. Do not use it to find nodes:
    scene_overview mode "search" does that.

    A path is the full path of a node, for example "/obj/geo1/mountain1". A
    path that is not a node stops the call with an error, and the selection
    stays as it was.

    Returns JSON with the selected paths.
    """
    return call_json("select", {"paths": paths})
