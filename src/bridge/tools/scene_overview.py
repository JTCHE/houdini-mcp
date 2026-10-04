"""scene_overview — the lists that say what is in the scene."""
from mcp.types import ToolAnnotations

from ..connection import call_json

ANNOTATIONS = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)

PARAMS = {
    "mode": 'One of "scene", "network", "children", "search", "node_types", "errors", '
            '"materials", "lights", "takes", "caches", "render_nodes", "viewports".',
    "path": 'A node path such as "/obj" or "/obj/geo1": the network to list or to search.',
    "pattern": "search: the name to match, with * and ? as wildcards.",
    "node_type": 'search: keep the nodes of this type, for example "null".',
    "category": 'node_types: the context, for example "Sop", "Object", "Lop" or "Driver".',
    "recursive": "children: also list the children of the children.",
}


def tool(mode: str = "scene", path: str = None, pattern: str = None,
         node_type: str = None, category: str = None, recursive: bool = False) -> str:
    """List what the scene holds. Start here, before you touch a node.

    Use it to find a node path, to see the shape of a network, or to learn
    which node types this Houdini has.

    Do not use it to read one node in detail: node_inspect does that. Do not
    use it to read geometry: geometry_inspect does that.

    mode:
        "scene"        — file, frame range, counts, and the top of the tree.
        "network"      — the children of one network, with their connections.
        "children"     — the children of `path`. recursive=True walks down.
        "search"       — nodes whose name matches `pattern`, under `path`.
                         node_type filters by type name.
        "node_types"   — the node types this Houdini has, for one `category`
                         such as "Sop", "Object", "Lop", "Driver".
        "errors"       — every node under `path` that has a cook error.
        "materials"    — the materials in `path` (default /mat) and the types.
        "lights"       — the lights on the USD stage of the LOP node `path`.
        "takes"        — the takes, and which take is current.
        "caches"       — file caches under `path` and their state on disk.
        "render_nodes" — the ROP nodes in /out.
        "viewports"    — the panes, and what the scene viewer shows.

    Returns JSON. A path that does not exist comes back as an error, not as an
    empty list.
    """
    return call_json("scene_overview", {
        "mode": mode, "path": path, "pattern": pattern,
        "node_type": node_type, "category": category, "recursive": recursive,
    })
