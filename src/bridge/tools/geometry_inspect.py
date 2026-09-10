"""geometry_inspect — what a node cooked: points, prims, attributes, images."""
from typing import List

from ..connection import call_json


def tool(path: str, mode: str = "summary", start: int = 0, count: int = 100,
         attribs: List[str] = None, attrib_name: str = None,
         attrib_class: str = "point", group_name: str = None,
         group_type: str = "point", prim_index: int = 0,
         position: List[float] = None, plane_name: str = "C",
         format: str = "obj", output: str = None) -> str:
    """Read the geometry that a node produces. This cooks the node.

    Use it to confirm that a node made what you expected: the point count, an
    attribute that a wrangle wrote, the size of the bounding box.

    Do not use it to read parameters: node_inspect does that.

    path: the SOP or COP node to read.

    mode:
        "summary"       — counts, attributes, groups, bounds. Start here.
        "points"        — `count` points from `start`, with `attribs`.
        "prims"         — `count` primitives from `start`.
        "attrib"        — the values of `attrib_name` on `attrib_class`, one of
                          "point", "prim", "vertex", "detail".
        "groups"        — the groups of `group_type`.
        "group_members" — the members of `group_name`.
        "bbox"          — the bounding box.
        "intrinsics"    — the intrinsic values of primitive `prim_index`.
        "nearest"       — the point nearest to `position`, for example [0,1,0].
        "image"         — a COP node: resolution, planes, and the plane
                          `plane_name`.
        "volume"        — the VDB grids in a COP node.
        "export"        — write the geometry to disk. `format` is "obj",
                          "bgeo" or another that Houdini writes, and `output`
                          is the file path.

    Returns JSON. A large read is slow: keep `count` small and page with
    `start`.
    """
    return call_json("geometry_inspect", {
        "path": path, "mode": mode, "start": start, "count": count,
        "attribs": attribs, "attrib_name": attrib_name, "attrib_class": attrib_class,
        "group_name": group_name, "group_type": group_type, "prim_index": prim_index,
        "position": position, "plane_name": plane_name, "format": format,
        "output": output,
    }, timeout=180.0)
