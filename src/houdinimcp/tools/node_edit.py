"""Make, move, name, delete and flag nodes.

Every mode takes one item or a list of items. Houdini adds a numeric suffix
when a name is already used, so each result carries the path that Houdini gave.
"""
from . import as_list, unknown_mode
from ..handlers import chops, cops, lop, materials, nodes, takes, vex, viewport

MUTATES = True

MODES = ("create", "delete", "copy", "move", "rename", "flags", "color", "layout",
         "wrangle", "material", "assign_material", "take", "current_network")


def run(items=None, mode="create", **defaults):
    """Run one mode over one item or a list of items.

    An item is a dictionary of the arguments for the mode. Arguments given
    outside `items` are defaults for every item.
    """
    given = as_list(items) or [{}]
    results = []
    for item in given:
        arguments = {**defaults, **item}
        try:
            results.append(_one(mode, arguments))
        except Exception as error:
            results.append({"error": f"{type(error).__name__}: {error}", "item": arguments})
    return results[0] if len(results) == 1 else {"count": len(results), "results": results}


def _one(mode, item):
    if mode == "create":
        context = item.get("context", "sop")
        parent_path = item["parent_path"]
        node_type = item["node_type"]
        name = item.get("name")
        if context == "cop":
            return cops.create_cop_node(parent_path, node_type, name)
        if context == "chop":
            return chops.create_chop_node(parent_path, node_type, name)
        if context == "lop":
            return lop.create_lop_node(parent_path, node_type, name)
        if context == "material_network":
            return materials.create_material_network(parent_path, name or "matnet")
        return nodes.create_node(node_type, parent_path, name,
                                 item.get("position"), item.get("parameters"))
    if mode == "delete":
        return nodes.delete_node(item["path"])
    if mode == "copy":
        return nodes.copy_node(item["path"], item["destination_path"])
    if mode == "move":
        if "destination_path" in item:
            return nodes.move_node(item["path"], item["destination_path"])
        return nodes.modify_node(item["path"], position=item.get("position"))
    if mode == "rename":
        return nodes.rename_node(item["path"], item["new_name"])
    if mode == "flags":
        target = item["path"]
        setter = cops.set_cop_flags if item.get("context") == "cop" else nodes.set_node_flags
        return setter(target, item.get("display"), item.get("render"), item.get("bypass"))
    if mode == "color":
        return nodes.set_node_color(item["path"], item["color"])
    if mode == "layout":
        return nodes.layout_children(item.get("path", "/obj"))
    if mode == "wrangle":
        if "code" in item and "path" in item:
            return vex.set_wrangle_code(item["path"], item["code"])
        if item.get("attrib_name"):
            return vex.create_vex_expression(item["parent_path"], item["attrib_name"],
                                             item["expression"], item.get("run_over", "Points"))
        return vex.create_wrangle(item["parent_path"], item.get("wrangle_type", "attribwrangle"),
                                  item.get("name"), item.get("code", ""))
    if mode == "material":
        return nodes.set_material(item["path"], item.get("material_type", "principledshader"),
                                  item.get("name"), item.get("parameters"))
    if mode == "assign_material":
        return materials.assign_material(item["path"], item["material_path"])
    if mode == "take":
        if item.get("name"):
            return takes.create_take(item["name"], item.get("parent_name"))
        return takes.set_current_take(item["take_name"])
    if mode == "current_network":
        return viewport.set_current_network(item["path"])
    raise unknown_mode(mode, MODES)
