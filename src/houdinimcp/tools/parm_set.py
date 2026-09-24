"""Write parameters: values, expressions, keyframes, links, locks, spares.

A write can be accepted and have no effect, so each result says what the
parameter holds after the write.
"""
from . import items_of, unknown_mode
from ..handlers import animation, chops, parameters, rendering, snapshots, spares

MUTATES = True

MODES = ("value", "press", "expression", "keyframe", "keyframes", "delete_keyframe",
         "revert", "lock", "link", "spare", "render_settings", "chop_export", "snapshot",
         "restore", "diff")


def run(items=None, mode="value", **defaults):
    """Run one mode over one item or a list of items."""
    results = []
    for arguments in items_of(mode, items, defaults):
        try:
            results.append(_one(mode, arguments))
        except Exception as error:
            results.append({"error": f"{type(error).__name__}: {error}", "item": arguments})
    return results[0] if len(results) == 1 else {"count": len(results), "results": results}


def _one(mode, item):
    if mode == "value":
        follow = item.get("follow_reference", False)
        if "parameters" in item:
            return parameters.set_parameters(item["path"], item["parameters"], follow)
        return parameters.set_parameter(item["path"], item["parm"], item["value"], follow)
    if mode == "press":
        return parameters.press_button(item["path"], item["parm"])
    if mode == "expression":
        from ..handlers import nodes
        return nodes.set_expression(item["path"], item["parm"], item["expression"],
                                    item.get("language", "hscript"))
    if mode == "keyframe":
        return animation.set_keyframe(item["path"], item["parm"], item["frame"], item["value"])
    if mode == "keyframes":
        return animation.set_keyframes(item["path"], item["parm"], item["keyframes"])
    if mode == "delete_keyframe":
        return animation.delete_keyframe(item["path"], item["parm"], item["frame"])
    if mode == "revert":
        return parameters.revert_parameter(item["path"], item["parm"])
    if mode == "lock":
        return parameters.lock_parameter(item["path"], item["parm"], item.get("locked", True))
    if mode == "link":
        return parameters.link_parameters(item["src_path"], item["src_parm"],
                                          item["path"], item["parm"])
    if mode == "spare":
        specs = item.get("parameters") or [{
            key: given for key, given in (
                ("name", item["name"]), ("label", item.get("label")),
                ("type", item.get("parm_type")), ("default", item.get("default")),
                ("expression", item.get("expression"))) if given is not None}]
        return spares.add_spare_parameters(item["path"], specs)
    if mode == "render_settings":
        return rendering.set_render_settings(item["path"], item["settings"])
    if mode == "chop_export":
        return chops.export_chop_to_parm(item["chop_path"], item["channel_name"],
                                         item["path"], item["parm"])
    if mode == "snapshot":
        return snapshots.snapshot(item["name"], item.get("paths") or [item["path"]])
    if mode == "restore":
        return snapshots.restore(item["name"], _paths(item))
    if mode == "diff":
        return snapshots.diff(item["name"], _paths(item))
    raise unknown_mode(mode, MODES)


def _paths(item):
    """The nodes a restore or a diff is limited to, or None for the whole record."""
    return item.get("paths") or ([item["path"]] if item.get("path") else None)
