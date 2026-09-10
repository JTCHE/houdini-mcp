"""The USD stage of a LOP node: prims, layers, attributes, composition."""
from . import unknown_mode
from ..handlers import lop

MUTATES = False

MODES = ("stage", "prims", "prim", "search", "layer", "attribute", "composition",
         "variants", "stats", "modified", "lights")


def run(path, mode="stage", prim_path=None, pattern=None, type_name=None,
        attr_name=None, root_prim="/", max_depth=3, layer_index=0, count=10,
        include_attrs=False):
    if mode == "stage":
        return lop.lop_stage_info(path)
    if mode == "prims":
        return lop.list_usd_prims(path, root_prim, max_depth)
    if mode == "prim":
        _needs(prim_path, "prim")
        return lop.lop_prim_get(path, prim_path, include_attrs)
    if mode == "search":
        if not pattern:
            raise ValueError("mode 'search' needs a pattern.")
        return lop.lop_prim_search(path, pattern, type_name)
    if mode == "layer":
        return {"layers": lop.lop_layer_info(path),
                "inspected": lop.inspect_usd_layer(path, layer_index)}
    if mode == "attribute":
        _needs(prim_path, "attribute")
        if not attr_name:
            raise ValueError("mode 'attribute' needs attr_name.")
        return lop.get_usd_attribute(path, prim_path, attr_name)
    if mode == "composition":
        _needs(prim_path, "composition")
        return lop.get_usd_composition(path, prim_path)
    if mode == "variants":
        _needs(prim_path, "variants")
        return lop.get_usd_variants(path, prim_path)
    if mode == "stats":
        _needs(prim_path, "stats")
        return lop.get_usd_prim_stats(path, prim_path)
    if mode == "modified":
        return lop.get_last_modified_prims(path, count)
    if mode == "lights":
        return lop.list_lights(path)
    raise unknown_mode(mode, MODES)


def _needs(prim_path, mode):
    if not prim_path:
        raise ValueError(f"mode '{mode}' needs prim_path, for example '/World/geo'.")
