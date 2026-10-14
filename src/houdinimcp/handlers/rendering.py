"""ROP nodes: list them, read and write their settings, and start a render."""

import hou

from . import karma, parameters


def list_render_nodes():
    """List all ROP (render) nodes in the scene."""
    out_node = hou.node("/out")
    if not out_node:
        return {"count": 0, "nodes": []}
    nodes = []
    for child in out_node.children():
        nodes.append({
            "name": child.name(),
            "path": child.path(),
            "type": child.type().name(),
        })
    return {"count": len(nodes), "nodes": nodes}


def get_render_settings(path):
    """The output, camera, resolution and range of a ROP node, the engine that
    really renders, and the changed render settings split into the ones that
    engine reads and the ones it ignores."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    settings = {}
    for parm_name in ["camera", "picture", "outputimage", "res_overridex", "res_overridey",
                      "override_res", "res_scale", "trange", "f1", "f2", "f3"]:
        parm = node.parm(parm_name)
        if parm:
            settings[parm_name] = str(parm.eval())
    report = {"path": path, "type": node.type().name(), "settings": settings}
    report.update(_engine_report(node))
    return report


def _lop(rop):
    """The LOP node whose stage a USD Render ROP renders, or None."""
    if rop.parm("loppath") is not None and rop.evalParm("loppath"):
        return rop.node(rop.evalParm("loppath"))
    if rop.type().category() == hou.lopNodeTypeCategory():
        return rop.input(0)
    return None


def _prim_delegate(rop, lop):
    """husk:default_delegate on the render settings prim that the ROP uses."""
    try:
        from pxr import UsdRender
        stage = lop.stage()
        wanted = rop.evalParm("rendersettings") if rop.parm("rendersettings") else ""
        prim = stage.GetPrimAtPath(wanted) if wanted else None
        if not prim:
            settings = UsdRender.Settings.GetStageRenderSettings(stage)
            prim = settings.GetPrim() if settings else None
        if not prim:
            prim = next((one for one in stage.Traverse()
                         if one.GetTypeName() == "RenderSettings"), None)
        attribute = prim.GetAttribute("husk:default_delegate") if prim else None
        return (attribute.Get() if attribute else None), (prim.GetPath() if prim else None)
    except (ImportError, hou.Error, AttributeError):
        return None, None


def _delegate(rop):
    """(render delegate, where it comes from) of the render that `rop` starts."""
    if rop.parm("renderer") is not None:
        value = rop.evalParm("renderer")
        if value != "default_delegate":
            return value, f"{rop.path()} renderer"
        lop = _lop(rop)
        prim_value, prim = _prim_delegate(rop, lop) if lop else (None, None)
        if prim_value:
            return prim_value, (f"husk:default_delegate on {prim}; the ROP renderer is "
                                f"'default_delegate'")
        return "BRAY_HdKarma", ("Houdini's default delegate, Karma CPU: neither the ROP nor "
                                "the render settings prim names one")
    if karma.is_settings(rop):
        engine = rop.evalParm("engine")
        return ("BRAY_HdKarmaXPU" if engine == "xpu" else "BRAY_HdKarma"), f"{rop.path()} engine"
    return None, None


def _settings_nodes(rop):
    """The Karma settings nodes that feed the render: the Karma ROP itself, or
    the Karma Render Settings LOPs above the stage of a USD Render ROP."""
    if karma.is_settings(rop):
        return [rop]
    found, seen, todo = [], set(), [_lop(rop)]
    while todo and len(seen) < 2000:
        node = todo.pop()
        if node is None or node.path() in seen:
            continue
        seen.add(node.path())
        if karma.is_settings(node):
            found.append(node)
        todo += [one for one in node.inputs() if one is not None]
    return found


def _engine_report(rop):
    renderer, source = _delegate(rop)
    if renderer is None:
        return {}
    engine = karma.DELEGATES.get(renderer)
    report = {"renderer": renderer, "engine": engine, "engine_from": source}
    if engine is None:
        return report
    warnings, read, ignored = [], {}, {}
    for node in _settings_nodes(rop):
        own = node.evalParm("engine")
        if own != engine and node != rop:
            warnings.append(f"{node.path()} says engine = {own}, but the render runs on Karma "
                            f"{engine.upper()} ({source}). Settings that only "
                            f"{own.upper()} reads do nothing. Set the ROP renderer to "
                            f"BRAY_HdKarma{'XPU' if own == 'xpu' else ''}, or the engine "
                            f"of the node to {engine}.")
        for parm in node.parms():
            template = parm.parmTemplate()
            if template.type() in (hou.parmTemplateType.Folder, hou.parmTemplateType.FolderSet,
                                   hou.parmTemplateType.Label,
                                   hou.parmTemplateType.Separator) or parm.isAtDefault() \
                    or parm.isMultiParmInstance() or parm.name() == "engine":
                continue
            name = parm.path() if node != rop else parm.name()
            found = parameters.state(parm, {"engine": engine})
            rule = found.get("hidden") or found.get("disabled")
            value = parm.evalAsString()
            # A setting hidden by a rule that does not name the engine is
            # inert for another reason, and not part of this split.
            if found.get("ignored") or rule and "engine" in rule:
                ignored[name] = {"value": value,
                                 "why": found.get("ignored") or f"hidden or disabled while {rule}"}
            elif not rule:
                read[name] = value
    if not karma.xpu_labels() and engine == "xpu":
        warnings.append("The help of this Houdini is not installed, so the settings that XPU "
                        "ignores and that it does not hide are not listed.")
    report.update({"changed_settings_read": read, "changed_settings_ignored": ignored})
    if warnings:
        report["warnings"] = warnings
    return report


def set_render_settings(path, settings):
    """Set render settings on a ROP node."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    changes = []
    for name, value in settings.items():
        parm = node.parm(name)
        if parm:
            parm.set(value)
            changes.append(name)
    return {"path": path, "changed": changes}


def create_render_node(render_type="opengl", name=None, parent_path="/out"):
    """Create a ROP node."""
    parent = hou.node(parent_path)
    if not parent:
        raise ValueError(f"Parent not found: {parent_path}")
    node = parent.createNode(render_type, node_name=name)
    return {"path": node.path(), "name": node.name(), "type": render_type}


_gl_rendered = False


def start_render(path, frame_range=None):
    """Start a render from a ROP node."""
    global _gl_rendered
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    if node.type().name() == "opengl" and not hou.isUIAvailable() \
            and hou.applicationVersion()[0] >= 22:
        # hython 22.0 stops with a segmentation fault on the second OpenGL ROP
        # render in one process, and the unsaved scene is lost.
        if _gl_rendered:
            raise RuntimeError(
                "This hython already rendered an OpenGL ROP once. hython 22.0 stops "
                "with a segmentation fault on the second one, and the scene is lost. "
                "Render the whole range in one call, or use capture (it draws in a "
                "new hython).")
        _gl_rendered = True
    if frame_range and len(frame_range) == 2:
        node.render(frame_range=(frame_range[0], frame_range[1]))
    else:
        node.render()
    return {"path": path, "rendering": True}


def get_render_progress(path):
    """Get render progress from a ROP node."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    return {
        "path": path,
        "is_cooking": node.isCooking() if hasattr(node, "isCooking") else False,
    }
