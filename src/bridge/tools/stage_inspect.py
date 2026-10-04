"""stage_inspect — the USD stage that a LOP node makes."""
from typing import Dict, List, Union

from mcp.types import ToolAnnotations

from ..connection import call_json

ANNOTATIONS = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)

PARAMS = {
    "path": "The LOP node whose stage to read.",
    "mode": 'One of "stage", "prims", "prim", "search", "layer", "attribute", '
            '"composition", "variants", "stats", "modified", "lights", "transform".',
    "prim_path": 'prim, attribute, composition, variants, stats, transform: the prim, for '
                 'example "/world/geo/rock".',
    "pattern": "search: the prim path to match, with * as a wildcard.",
    "type_name": 'search: keep the prims of this type, for example "Mesh" or "SphereLight".',
    "attr_name": 'attribute: the attribute to read, for example "points".',
    "root_prim": "prims: the prim where the tree starts.",
    "max_depth": "prims: how many levels of the tree come back.",
    "layer_index": "layer: which layer of the stack, from 0 (the strongest).",
    "count": "modified: how many prims come back.",
    "include_attrs": "prim: also return the attributes of the prim.",
    "frames": "Read at another frame, or at several: one frame, a list, or "
              '{"start": 1, "end": 10, "step": 2}. The playbar goes back after.',
}


def tool(path: str, mode: str = "stage", prim_path: str = None, pattern: str = None,
         type_name: str = None, attr_name: str = None, root_prim: str = "/",
         max_depth: int = 3, layer_index: int = 0, count: int = 10,
         include_attrs: bool = False,
         frames: Union[float, List[float], Dict[str, float]] = None) -> str:
    """Read the USD stage at a LOP node. This cooks the node.

    Use it in a Solaris (LOP) network to see the prims, the layers and the
    composition that a node produces.

    Do not use it for SOP geometry: geometry_inspect does that.

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
        "transform"   — where `prim_path` is in the world: translate, rotate
                        and scale composed through every parent. With
                        `frames`, the path of a moving prim.

    Returns JSON.
    """
    return call_json("stage_inspect", {
        "path": path, "mode": mode, "prim_path": prim_path, "pattern": pattern,
        "type_name": type_name, "attr_name": attr_name, "root_prim": root_prim,
        "max_depth": max_depth, "layer_index": layer_index, "count": count,
        "include_attrs": include_attrs, "frames": frames,
    }, timeout=180.0)
