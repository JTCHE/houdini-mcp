"""stage_inspect — the USD stage that a LOP node makes."""
from ..connection import call_json


def tool(path: str, mode: str = "stage", prim_path: str = None, pattern: str = None,
         type_name: str = None, attr_name: str = None, root_prim: str = "/",
         max_depth: int = 3, layer_index: int = 0, count: int = 10,
         include_attrs: bool = False) -> str:
    """Read the USD stage at a LOP node. This cooks the node.

    Use it in a Solaris (LOP) network to see the prims, the layers and the
    composition that a node produces.

    Do not use it for SOP geometry: geometry_inspect does that.

    path: the LOP node whose stage you want to read.

    mode:
        "stage"       — the stage: prim count, layers, the default prim.
        "prims"       — the prim tree from `root_prim`, `max_depth` deep.
        "prim"        — one prim at `prim_path`. include_attrs=True adds its
                        attributes.
        "search"      — prims whose path matches `pattern`, filtered by
                        `type_name` such as "Mesh" or "SphereLight".
        "layer"       — the layer stack, and the layer at `layer_index`.
        "attribute"   — the value of `attr_name` on `prim_path`.
        "composition" — where the opinions on `prim_path` come from.
        "variants"    — the variant sets on `prim_path` and the selection.
        "stats"       — counts under `prim_path`.
        "modified"    — the last `count` prims that this node changed. Use it
                        to see what one LOP did.
        "lights"      — the lights on the stage.

    Returns JSON.
    """
    return call_json("stage_inspect", {
        "path": path, "mode": mode, "prim_path": prim_path, "pattern": pattern,
        "type_name": type_name, "attr_name": attr_name, "root_prim": root_prim,
        "max_depth": max_depth, "layer_index": layer_index, "count": count,
        "include_attrs": include_attrs,
    }, timeout=180.0)
