"""geometry_inspect — what a node cooked: points, prims, attributes, volumes."""
from typing import Any, Dict, List, Union

from mcp.types import ToolAnnotations

from ..connection import call_json

# Only "export" writes, and only the file at `output`.
ANNOTATIONS = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)

PARAMS = {
    "path": "The SOP or COP node to read, or a list. A list keeps going after a node that "
            "fails, and each result names its path.",
    "mode": 'One of "summary", "points", "prims", "attrib", "groups", "group_members", '
            '"bbox", "intrinsics", "nearest", "skeleton", "compare", "try", "volume_stats", '
            '"volume_voxels", "volume_sample", "volume_compare", "image", "volume", "export".',
    "start": "points, prims, attrib: the first element. Page with it.",
    "count": "points, prims: how many elements. Keep it small: a large read is slow.",
    "attribs": 'points: the attributes to return, for example ["P", "Cd"].',
    "attrib_name": "attrib: the attribute to read.",
    "attrib_class": 'attrib: "point", "prim", "vertex" or "detail".',
    "group_name": "group_members: the group to read.",
    "group_type": 'groups, group_members: "point", "prim", "vertex" or "edge".',
    "prim_index": "intrinsics: the primitive to read.",
    "position": "nearest: [x, y, z].",
    "plane_name": 'image: the COP plane to read, for example "C".',
    "format": 'export: the file type, for example "obj" or "bgeo".',
    "output": "export: the file path to write.",
    "frames": 'Read at other frames, without moving the playbar: one frame, a list, or '
              '{"start": 1001, "end": 1010, "step": 2}. One answer for each frame.',
    "unique": "attrib: return each value that occurs and how many elements carry it. That "
              "is how you find the pieces in a geometry.",
    "against": "compare: the node to compare with. volume_compare: the field whose bands "
               "hold the field `name`.",
    "match_attrib": "compare: the attribute that pairs the points of the two nodes, not "
                    "their order.",
    "pattern": "skeleton: keep the joints whose name matches.",
    "name": "volume_stats: one volume to read. volume_voxels, volume_compare: the field.",
    "names": "volume_sample: the fields to read.",
    "positions": "volume_sample: the [x, y, z] points to read at.",
    "from_node": "volume_sample: read at the points of this node. volume_compare: the node "
                 "that holds `against`, such as a collider SDF.",
    "steps": 'try: a list of {"node_type": ..., "parameters": {...}} to run on the geometry '
             "as verbs. Nothing changes in the scene.",
    "bins": "volume_stats, volume_sample, volume_compare: a count of equal bands, or a list "
            "of band edges, for example [-1, 0, 0.05, 0.15, 0.25].",
    "limit": "attrib: how many values (10). volume_voxels: how many numbers before the array "
             "is thinned. volume_sample: return the values when there are at most this many "
             "(1000).",
    "reduce": 'volume_voxels: one answer instead of the array: "sum", "mean", "max", "min", '
              '"project_x", "project_y" or "project_z".',
    "threshold": "volume_stats, volume_sample: count the voxels below and above it. "
                 "volume_stats also gives the world box of the voxels above it.",
}


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
