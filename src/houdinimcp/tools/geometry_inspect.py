"""What a node cooked: points, primitives, attributes, groups, volumes, images.

Every mode takes `frames`. The result then holds one answer for each frame, and
the playbar does not move: a read never changes the frame that the user is on.
"""
from . import unknown_mode
from ..handlers import cops, geometry, timing, volumes

MUTATES = False

MODES = ("summary", "points", "prims", "attrib", "groups", "group_members", "bbox",
         "intrinsics", "nearest", "skeleton", "compare", "try", "volume_stats",
         "volume_voxels", "volume_sample", "volume_compare", "image", "volume", "export")


def run(path, mode="summary", frames=None, **options):
    """Read one node, or each node of a list. Every result of a list names
    its path, and a node that fails does not stop the others."""
    if isinstance(path, str):
        return _read(path, mode, frames, options)
    results = []
    for one in path:
        try:
            results.append({"path": one, "result": _read(one, mode, frames, options)})
        except Exception as error:
            results.append({"path": one, "error": f"{type(error).__name__}: {error}"})
    return {"count": len(results), "nodes": results}


def _read(path, mode, frames, options):
    if frames:
        return timing.at_frames(frames, lambda: _one(path, mode, options))
    return _one(path, mode, options)


def _one(path, mode, options, frame=None):
    """One read. `frame` stays None: at_frames moves the playbar instead, so
    that a mode which reads more than one node reads them at the same time."""
    def want(name, default=None):
        value = options.get(name, default)
        return default if value is None else value

    if mode == "summary":
        return geometry.get_geo_summary(path, frame)
    if mode == "points":
        return geometry.get_points(path, want("start", 0), want("count", 100),
                                   want("attribs"), frame)
    if mode == "prims":
        return geometry.get_prims(path, want("start", 0), want("count", 100),
                                  want("attribs"), frame)
    if mode == "attrib":
        if not want("attrib_name"):
            raise ValueError("mode 'attrib' needs attrib_name.")
        return geometry.get_attrib_values(path, want("attrib_name"),
                                          want("attrib_class", "point"), frame,
                                          want("unique", False), want("start", 0),
                                          want("limit", 10))
    if mode == "groups":
        return geometry.get_groups(path, want("group_type", "point"), frame)
    if mode == "group_members":
        if not want("group_name"):
            raise ValueError("mode 'group_members' needs group_name.")
        return geometry.get_group_members(path, want("group_name"),
                                          want("group_type", "point"), frame)
    if mode == "bbox":
        return geometry.get_bounding_box(path, frame)
    if mode == "intrinsics":
        return geometry.get_prim_intrinsics(path, want("prim_index", 0), frame)
    if mode == "nearest":
        if not want("position"):
            raise ValueError("mode 'nearest' needs position, for example [0, 1, 0].")
        return geometry.find_nearest_point(path, want("position"), frame)
    if mode == "skeleton":
        return geometry.get_skeleton(path, frame, want("pattern"))
    if mode == "compare":
        if not want("against"):
            raise ValueError("mode 'compare' needs against, the path of the second node.")
        return geometry.compare_nodes(path, want("against"), want("match_attrib", "name"),
                                      want("attribs"), frame)
    if mode == "try":
        if not want("steps"):
            raise ValueError('mode \'try\' needs steps, for example '
                             '[{"node_type": "unpackusd", "parameters": {}}].')
        return geometry.try_nodes(path, want("steps"), frame)
    if mode == "volume_stats":
        return volumes.stats(path, want("name"), frame, want("bins", 0), want("threshold"))
    if mode == "volume_voxels":
        if not want("name"):
            raise ValueError("mode 'volume_voxels' needs name, the name of the field.")
        return volumes.voxels(path, want("name"), frame, want("limit", 20000),
                              want("reduce"))
    if mode == "volume_sample":
        if not want("names"):
            raise ValueError("mode 'volume_sample' needs names, the fields to read.")
        return volumes.sample(path, want("names"), want("positions"), want("from_node"),
                              frame, want("limit", 1000), want("bins", 10), want("threshold"))
    if mode == "volume_compare":
        if not want("name") or not want("against"):
            raise ValueError("mode 'volume_compare' needs name and against, two field names.")
        return volumes.compare_fields(path, want("name"), want("against"), frame,
                                      want("bins", 10), want("from_node"))
    if mode == "image":
        return {"info": cops.get_cop_info(path), "geometry": cops.get_cop_geometry(path),
                "layer": cops.get_cop_layer(path, want("plane_name", "C"))}
    if mode == "volume":
        return cops.get_cop_vdb(path)
    if mode == "export":
        return geometry.geo_export(path, want("format", "obj"), want("output"), frame)
    raise unknown_mode(mode, MODES)
