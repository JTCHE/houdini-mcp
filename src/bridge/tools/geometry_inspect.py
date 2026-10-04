"""geometry_inspect — what a node cooked: points, prims, attributes, volumes."""
from typing import Any, Dict, List, Union

from ..connection import call_json


def tool(path: Union[str, List[str]], mode: str = "summary", start: int = 0, count: int = 100,
         attribs: List[str] = None, attrib_name: str = None,
         attrib_class: str = "point", group_name: str = None,
         group_type: str = "point", prim_index: int = 0,
         position: List[float] = None, plane_name: str = "C",
         format: str = "obj", output: str = None,
         frames: Union[float, List[float], Dict[str, float]] = None,
         unique: bool = False, against: str = None, match_attrib: str = "name",
         pattern: str = None, name: str = None, names: List[str] = None,
         positions: List[List[float]] = None, from_node: str = None,
         steps: List[Dict[str, Any]] = None, bins: Union[int, List[float]] = None, limit: int = None,
         reduce: str = None, threshold: float = None) -> str:
    """Read the geometry that a node produces. This cooks the node.

    Use it to confirm that a node made what you expected: the point count, an
    attribute that a wrangle wrote, the shape of a volume, the size of the
    bounding box.

    Do not use it to read parameters: node_inspect does that.

    path: the SOP or COP node to read, or a list of them. A list keeps going
    after a node that fails, and each result names its path.

    frames: read at other frames without moving the playbar of the user. One
    number, a list, or {"start": 1001, "end": 1010, "step": 2}. The result then
    holds one answer for each frame. The user stays on the frame they were on.

    mode:
        "summary"        — counts, attributes, groups, volumes, bounds. Start
                           here. An empty result carries the errors and the
                           warnings of the node, which is where the reason is.
        "points"         — `count` points from `start`, with `attribs`.
        "prims"          — `count` primitives from `start`.
        "attrib"         — the values of `attrib_name` on `attrib_class`
                           ("point", "prim", "vertex", "detail"): min, max
                           and mean of each component over every element,
                           and `limit` (10) values from `start`. A vector
                           attribute keeps its shape. unique=True returns each
                           value that occurs and how many elements carry it,
                           which is how you find the pieces in a geometry.
        "groups"         — the groups of `group_type`.
        "group_members"  — the members of `group_name`.
        "bbox"           — the bounding box.
        "intrinsics"     — the intrinsic values of primitive `prim_index`.
        "nearest"        — the point nearest to `position`, for example [0,1,0].
        "skeleton"       — a KineFX skeleton: each joint with its name, its
                           parent and its transform. `pattern` keeps the names
                           that match.
        "compare"        — the difference from the node at `against`. Points are
                           matched by `match_attrib` ("name" by default), not by
                           their order. Use it to prove that a new node gives
                           the result of the node it replaces.
        "try"            — run `steps`, a list of
                           {"node_type": ..., "parameters": {...}}, on the
                           geometry of `path` as verbs. Nothing changes in the
                           scene. Use it to learn what a node would make.
        "volume_stats"   — every volume or VDB: resolution, voxel size, the
                           extremes, the mean, the sum, percentiles. `name`
                           reads one, `bins` adds a histogram, `threshold`
                           counts the voxels below and above it and gives the
                           world box of the voxels above it.
        "volume_voxels"  — one field as an array indexed [z][y][x], with its
                           shape and its transform. `name` is the field.
                           `reduce` gives one answer instead: "sum", "mean",
                           "max", "min", or "project_x", "project_y",
                           "project_z" (the sum along that axis, a 2D array).
                           An array past `limit` numbers is thinned.
        "volume_sample"  — read `names` (fields) at `positions`, or at the
                           points of `from_node`, with no node added to the
                           scene. Returns min, max, mean, percentiles, a
                           histogram of `bins` (10), the counts on each side of
                           `threshold`, and the values when there are at most
                           `limit` (1000).
        "volume_compare" — how much of the field `name` sits in each band of the
                           field `against`. The answer to "how much smoke is
                           inside the collider". `from_node` holds `against`
                           when another node does, such as the collider SDF.
    bins: a count of equal bands, or a list of band edges, for example
    [-1, 0, 0.05, 0.15, 0.25] for inside, 0-5 cm, 5-15 cm and 15-25 cm.
        "image"          — a COP node: resolution, planes, and `plane_name`.
        "volume"         — the VDB grids in a COP node.
        "export"         — write the geometry to disk. `format` is "obj",
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
        "output": output, "frames": frames, "unique": unique, "against": against,
        "match_attrib": match_attrib, "pattern": pattern, "name": name, "names": names,
        "positions": positions, "from_node": from_node, "steps": steps, "bins": bins,
        "limit": limit, "reduce": reduce, "threshold": threshold,
    }, timeout=300.0)
