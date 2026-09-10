"""What a node cooked: points, primitives, attributes, groups, bounds, images."""
from . import unknown_mode
from ..handlers import cops, geometry

MUTATES = False

MODES = ("summary", "points", "prims", "attrib", "groups", "group_members", "bbox",
         "intrinsics", "nearest", "image", "volume", "export")


def run(path, mode="summary", start=0, count=100, attribs=None, attrib_name=None,
        attrib_class="point", group_name=None, group_type="point", prim_index=0,
        position=None, plane_name="C", format="obj", output=None):
    if mode == "summary":
        return geometry.get_geo_summary(path)
    if mode == "points":
        return geometry.get_points(path, start, count, attribs)
    if mode == "prims":
        return geometry.get_prims(path, start, count, attribs)
    if mode == "attrib":
        if not attrib_name:
            raise ValueError("mode 'attrib' needs attrib_name.")
        return geometry.get_attrib_values(path, attrib_name, attrib_class)
    if mode == "groups":
        return geometry.get_groups(path, group_type)
    if mode == "group_members":
        if not group_name:
            raise ValueError("mode 'group_members' needs group_name.")
        return geometry.get_group_members(path, group_name, group_type)
    if mode == "bbox":
        return geometry.get_bounding_box(path)
    if mode == "intrinsics":
        return geometry.get_prim_intrinsics(path, prim_index)
    if mode == "nearest":
        if not position:
            raise ValueError("mode 'nearest' needs position, for example [0, 1, 0].")
        return geometry.find_nearest_point(path, position)
    if mode == "image":
        return {"info": cops.get_cop_info(path), "geometry": cops.get_cop_geometry(path),
                "layer": cops.get_cop_layer(path, plane_name)}
    if mode == "volume":
        return cops.get_cop_vdb(path)
    if mode == "export":
        return geometry.geo_export(path, format, output)
    raise unknown_mode(mode, MODES)
