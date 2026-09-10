"""select — which nodes are selected."""
from typing import List, Union

from ..connection import call_json


def tool(paths: Union[str, List[str]] = None) -> str:
    """Read the node selection, or set it.

    Use it to see what the person works on before you change the scene, and to
    put your own result in front of them when you are done.

    paths: nothing reads the selection. One path or a list of paths replaces
    it. An empty list clears it.

    Returns JSON with the selected paths.
    """
    return call_json("select", {"paths": paths})
