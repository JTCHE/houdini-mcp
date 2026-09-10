"""Write parameters: values, expressions, keyframes, links, locks, spares.

A write can be accepted and have no effect, so each result says what the
parameter holds after the write.
"""
from . import as_list, unknown_mode
from ..handlers import animation, chops, parameters, rendering

MUTATES = True

MODES = ("value", "expression", "keyframe", "keyframes", "delete_keyframe", "revert",
         "lock", "link", "spare", "render_settings", "chop_export")


def run(items=None, mode="value", **defaults):
    """Run one mode over one item or a list of items."""
    results = []
    for item in as_list(items) or [{}]:
        arguments = {**defaults, **item}
        try:
            results.append(_one(mode, arguments))
        except Exception as error:
            results.append({"error": f"{type(error).__name__}: {error}", "item": arguments})
    return results[0] if len(results) == 1 else {"count": len(results), "results": results}


def _one(mode, item):
    if mode == "value":
        if "parameters" in item:
            return parameters.set_parameters(item["path"], item["parameters"])
        return parameters.set_parameter(item["path"], item["parm"], item["value"])
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
        if "parameters" in item:
            return parameters.create_spare_parameters(item["path"], item["parameters"])
        return parameters.create_spare_parameter(item["path"], item["name"], item["label"],
                                                 item["parm_type"], item.get("default"))
    if mode == "render_settings":
        return rendering.set_render_settings(item["path"], item["settings"])
    if mode == "chop_export":
        return chops.export_chop_to_parm(item["chop_path"], item["channel_name"],
                                         item["path"], item["parm"])
    raise unknown_mode(mode, MODES)
