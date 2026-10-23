"""ROP nodes: list them, read and write their settings, and start a render."""

import json
import os
import subprocess
import sys
import time

import hou

from .. import protocol
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


# The parameter that names the image, by ROP type: USD Render, Karma and
# OpenGL, Mantra, Composite.
OUTPUT_PARMS = ("outputimage", "picture", "vm_picture", "copoutput", "sopoutput", "lopoutput")
# How long a call waits for the images. The bridge gives up at 1800 s.
WAIT_LIMIT = 1700.0


def _output_parm(node):
    return next((node.parm(name) for name in OUTPUT_PARMS if node.parm(name) is not None), None)


def _frames(node, frame_range):
    """The frames that a render of `node` writes."""
    if frame_range:
        start, end = frame_range[0], frame_range[1]
        step = frame_range[2] if len(frame_range) > 2 else 1
    elif node.parm("trange") is not None and node.evalParm("trange") != 0:
        start, end, step = (node.evalParm(name) for name in ("f1", "f2", "f3"))
    else:
        return [hou.frame()]
    count = int(round((end - start) / (step or 1))) + 1
    return [start + index * step for index in range(max(count, 1))]


def _scale_values(node, res_scale):
    """{parameter: value} that make `node` render at `res_scale` of its size."""
    if node.parm("override_res") is not None and node.parm("res_scale") is not None:
        return {"override_res": "scale", "res_scale": res_scale * 100.0}
    if node.parm("override_camerares") is not None and node.parm("res_fraction") is not None:
        tokens = node.parm("res_fraction").parmTemplate().menuItems()
        for token in tokens:
            try:
                if abs(float(token) - res_scale) < 1e-3:
                    return {"override_camerares": 1, "res_fraction": token}
            except ValueError:
                continue
        raise ValueError(f"res_scale on a Karma ROP must be one of its fractions: "
                         f"{[token for token in tokens if token[:1].isdigit()]}.")
    raise ValueError(f"{node.path()} ({node.type().name()}) has no resolution scale. "
                     f"res_scale works on a USD Render ROP and a Karma ROP.")


def _hold(parms):
    """What `parms` hold now, keyframes included, to put back after."""
    held = []
    for parm in parms:
        keys = parm.keyframes()
        text = parm.parmTemplate().type() == hou.parmTemplateType.String
        held.append((parm, keys, None if keys else
                     (parm.unexpandedString() if text else parm.eval())))
    return held


def _put_back(held):
    for parm, keys, value in held:
        parm.deleteAllKeyframes()
        if keys:
            parm.setKeyframes(keys)
        else:
            parm.set(value)


def start_render(path, frame_range=None, output_path=None, res_scale=None, wait=False):
    """Render a ROP node. `output_path` and `res_scale` hold for this render
    only: the ROP gets its own values back when render() returns, which is
    after husk got its command line. With `wait`, a generator that returns when
    every image is complete, with a summary of husk:render_stats."""
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
    frames = _frames(node, frame_range)
    output = _output_parm(node)
    values = _scale_values(node, res_scale) if res_scale else {}
    if output_path:
        if output is None:
            raise ValueError(f"{node.path()} has none of the output parameters {OUTPUT_PARMS}.")
        if len(frames) > 1 and "$F" not in output_path:
            raise ValueError(f"{len(frames)} frames would all write {output_path}. Put $F4 in "
                             f"output_path.")
        values[output.name()] = output_path
    held = _hold([node.parm(name) for name in values])
    started = time.time()
    try:
        for name, value in values.items():
            node.parm(name).deleteAllKeyframes()
            node.parm(name).set(value)
        files = [output.evalAtFrame(frame) for frame in frames] if output else []
        files = [os.path.abspath(one) for one in files if one]
        if frame_range:
            node.render(frame_range=(frames[0], frames[-1],
                                     frames[1] - frames[0] if len(frames) > 1 else 1))
        else:
            node.render()
    finally:
        _put_back(held)
    report = {"path": path, "frames": [frames[0], frames[-1]],
              "files": files[:3] + ([f"... {len(files) - 3} more"] if len(files) > 3 else [])}
    if values:
        report["for_this_render_only"] = values
    if not wait:
        report["note"] = ("The render can go on in husk after this call. Use wait=true, or "
                          "render mode 'watch' with the file.")
        return report
    if not files:
        raise ValueError(f"wait needs the image file, and {node.path()} names none. Give "
                         f"output_path.")
    return _waited(report, files, started)


# A separate hython runs this: it opens the saved scene and renders the ROP
# with the same overrides as a render in the session.
BACKGROUND = r'''
import json, sys, hou
args = json.loads(sys.argv[1])
sys.path.insert(0, args["plugin"])
hou.hipFile.load(args["hip"], suppress_save_prompt=True, ignore_load_warnings=True)
from houdinimcp.handlers import rendering
print(json.dumps(rendering.start_render(args["path"], args["frame_range"], args["output_path"],
                                        args["res_scale"]), default=str), flush=True)
print("MCP: render done", flush=True)
'''


def start_background(path, frame_range=None, output_path=None, res_scale=None):
    """Render the ROP in a separate hython that opens the saved .hip file, so
    this session stays free while the stage cooks and husk renders."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    if not hou.isUIAvailable():
        # hython reports unsaved changes after every save, and it has no
        # window to keep free.
        raise ValueError("background=true is for a Houdini with a window. Render in this "
                         "session: drop background.")
    hip = hou.hipFile.path()
    if hou.hipFile.hasUnsavedChanges() or not os.path.isfile(hip):
        raise ValueError("A background render opens the .hip file on disk, and this session "
                         "has changes that are not in it. Save first (scene_file mode "
                         "'save', when the user agrees), or render in the session.")
    hython = os.path.join(hou.getenv("HFS"), "bin",
                          "hython.exe" if sys.platform == "win32" else "hython")
    folder = os.path.join(protocol.data_dir(), "renders")
    os.makedirs(folder, exist_ok=True)
    log = os.path.join(folder, f"{node.name()}_{time.strftime('%Y%m%d_%H%M%S')}.log")
    plugin = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    args = {"hip": hip, "plugin": plugin, "path": path, "frame_range": frame_range,
            "output_path": output_path, "res_scale": res_scale}
    detach = ({"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
              if sys.platform == "win32" else {"start_new_session": True})
    with open(log, "w") as handle:
        process = subprocess.Popen([hython, "-c", BACKGROUND, json.dumps(args)],
                                   stdout=handle, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, **detach)
    frames = _frames(node, frame_range)
    output = _output_parm(node)
    files = ([output_path.replace("$F4", f"{int(frame):04d}") for frame in frames] if output_path
             else [output.evalAtFrame(frame) for frame in frames] if output else [])
    return {"path": path, "background": True, "pid": process.pid, "log": log,
            "frames": [frames[0], frames[-1]],
            "files": files[:3] + ([f"... {len(files) - 3} more"] if len(files) > 3 else []),
            "note": "A separate hython renders the saved scene; this session stays free. "
                    "The log ends with 'MCP: render done'. Follow the images with render "
                    "mode 'watch' and output_path."}


def _waited(report, files, started):
    deadline = time.time() + WAIT_LIMIT
    while not all(_complete(one, started) for one in files):
        if time.time() > deadline:
            report["done"] = False
            report["note"] = (f"Not complete after {WAIT_LIMIT:.0f} s. Call render mode "
                              f"'watch' with the file, or start again with wait.")
            return report
        yield 2.0, None
    report["done"] = True
    report["seconds"] = round(time.time() - started, 1)
    stats = render_stats(files[-1])
    if stats:
        report["render_stats"] = stats
    return report


def _complete(path, started):
    """True when the image at `path` is written by this render and is final.
    Karma writes a snapshot while it renders; its stats say when it is done."""
    if not os.path.exists(path) or os.path.getmtime(path) < started - 1:
        return False
    raw = _raw_stats(path)
    if raw is None:
        return time.time() - os.path.getmtime(path) > 2
    return (raw.get("percent_complete") or 0) >= 100


def _raw_stats(path):
    """husk:render_stats of an image as a dictionary, or None."""
    try:
        import OpenImageIO
        image = OpenImageIO.ImageInput.open(path)
        if not image:
            return None
        try:
            text = image.spec().getattribute("husk:render_stats")
            seconds = image.spec().getattribute("renderTime")
        finally:
            image.close()
        if not text:
            return None
        raw = json.loads(text)
        raw["__seconds"] = seconds
        return raw
    except (ImportError, ValueError, OSError):
        return None


def render_stats(path):
    """The facts that matter in husk:render_stats: time, engine, devices and
    their share, shader compiles, memory, AOVs. None without the field."""
    raw = _raw_stats(path)
    if raw is None:
        return None
    stats = {"engine": raw.get("engine"), "delegate": raw.get("__delegate"),
             "render_seconds": raw.get("__seconds") or
             (raw.get("system_time") or {}).get("wallclock"),
             "time_to_first_pixel": raw.get("ttfp"),
             "percent_complete": raw.get("percent_complete"),
             "resolution": raw.get("resolution"), "camera": raw.get("render_camera"),
             "peak_memory_mb": round(((raw.get("system_memory") or {}).get("peak") or 0)
                                     / 2 ** 20),
             "aovs": [one.get("name") for one in raw.get("aov_buffers") or []]}
    devices = [{"name": one.get("xpu_device_label"), "type": one.get("xpu_device_type"),
                "share_percent": one.get("xpu_device_contrib"),
                "samples": one.get("xpu_device_samples"),
                **({"error": one["xpu_device_error"]} if one.get("xpu_device_error") else {})}
               for one in raw.get("xpu_devices") or []]
    if devices:
        stats["devices"] = devices
    compiles = raw.get("xpu_compiles")
    if compiles:
        stats["shader_compiles"] = {"count": compiles.get("count"),
                                    "shaders": compiles.get("count_shader"),
                                    "kernels": compiles.get("count_kernel"),
                                    "average_seconds": compiles.get("avg_time"),
                                    "longest_seconds": compiles.get("max_time"),
                                    "still_running": compiles.get("active")}
    idle = [one["name"] for one in devices
            if one["type"] != "EmbreeCPU" and not one["share_percent"]]
    if idle:
        compiling = compiles and (compiles.get("count") or compiles.get("active"))
        stats["warning"] = (f"{', '.join(idle)} did 0 % of the samples. " + (
            "XPU compiled shaders and kernels during this render, and while it compiles the "
            "CPU device renders alone. Render again: the compiles are cached."
            if compiling else
            "The render ended before the GPU started; a render this short says nothing "
            "about the speed of XPU."))
    return stats


def compare_images(path, reference):
    """The mean absolute difference of each AOV of two images."""
    import numpy
    import OpenImageIO

    def read(one):
        image = OpenImageIO.ImageInput.open(one)
        if not image:
            raise ValueError(f"Cannot read {one}: {OpenImageIO.geterror()}")
        try:
            return list(image.spec().channelnames), image.read_image("float")
        finally:
            image.close()

    names, pixels = read(path)
    reference_names, reference_pixels = read(reference)
    if pixels.shape[:2] != reference_pixels.shape[:2]:
        raise ValueError(f"The sizes differ: {pixels.shape[1]} x {pixels.shape[0]} and "
                         f"{reference_pixels.shape[1]} x {reference_pixels.shape[0]}.")
    groups = {}
    for index, name in enumerate(names):
        groups.setdefault(name.rsplit(".", 1)[0] if "." in name else "C", []).append(index)
    aovs, missing = {}, []
    for aov, indices in groups.items():
        other = [reference_names.index(names[i]) if names[i] in reference_names else None
                 for i in indices]
        if None in other:
            missing.append(aov)
            continue
        difference = numpy.abs(pixels[..., indices] - reference_pixels[..., other])
        aovs[aov] = {"mean_abs_difference": float(difference.mean()),
                     "max_abs_difference": float(difference.max()),
                     "reference_mean": float(numpy.abs(reference_pixels[..., other]).mean())}
    report = {"path": path, "reference": reference, "aovs": aovs}
    if missing:
        report["not_in_reference"] = missing
    return report


def get_render_progress(path):
    """Get render progress from a ROP node."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    return {
        "path": path,
        "is_cooking": node.isCooking() if hasattr(node, "isCooking") else False,
    }
