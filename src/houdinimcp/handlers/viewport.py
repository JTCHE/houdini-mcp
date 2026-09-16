"""Viewport and pane manipulation handlers."""
import os
from contextlib import contextmanager

import hou


def list_panes():
    """List all pane tabs in the desktop."""
    panes = []
    for tab in hou.ui.paneTabs():
        panes.append({
            "name": tab.name(),
            "type": str(tab.type()),
            "is_current": tab.isCurrentTab(),
        })
    return {"count": len(panes), "panes": panes}


def _shown_set(viewer):
    """The display set of what the viewer shows. Inside a SOP network that is the
    displayed SOP. In a LOP network (the stage) and at object level it is the
    scene geometry; there the DisplayModel set changes nothing on screen."""
    in_sops = viewer.pwd().childTypeCategory() == hou.sopNodeTypeCategory()
    settype = hou.displaySetType.DisplayModel if in_sops else hou.displaySetType.SceneObject
    return viewer.curViewport().settings().displaySet(settype)


def get_viewport_info():
    """Get current viewport settings."""
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if not viewer:
        raise RuntimeError("No scene viewer found")
    viewport = viewer.curViewport()
    in_lops = viewer.pwd().childTypeCategory() == hou.lopNodeTypeCategory()
    return {
        "name": viewport.name(),
        "type": str(viewport.type()),
        "camera": viewport.camera().path() if viewport.camera() else None,
        "shading": _shown_set(viewer).shadedMode().name(),
        "renderer": viewer.currentHydraRenderer() if in_lops else None,
    }


def set_viewport_camera(camera_path):
    """Set the viewport camera to a specific camera node."""
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if not viewer:
        raise RuntimeError("No scene viewer found")
    cam = hou.node(camera_path)
    if not cam:
        raise ValueError(f"Camera not found: {camera_path}")
    viewport = viewer.curViewport()
    viewport.setCamera(cam)
    return {"camera": camera_path}


def set_viewport_display(shading_mode=None, guide=None):
    """Set viewport display options (shading mode, guides)."""
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if not viewer:
        raise RuntimeError("No scene viewer found")
    viewport = viewer.curViewport()
    settings = viewport.settings()
    changes = []
    if shading_mode is not None:
        mode_map = {
            "wireframe": hou.glShadingType.Wire,
            "flat": hou.glShadingType.Flat,
            "smooth": hou.glShadingType.Smooth,
            "smooth_wire": hou.glShadingType.SmoothWire,
        }
        mode = mode_map.get(shading_mode)
        if mode is None:
            raise ValueError(f"Unknown shading: {shading_mode}. Use: {list(mode_map)}")
        _shown_set(viewer).setShadedMode(mode)
        changes.append(f"shading={shading_mode}")
    if guide is not None:
        settings.enableGuide(hou.viewportGuide.NodeGuides, guide)
        changes.append(f"guides={'on' if guide else 'off'}")
    return {"changes": changes}


def set_viewport_renderer(renderer):
    """Set the Hydra renderer of the scene viewer, for example "Karma CPU"
    or "Houdini VK". It applies to a viewer that shows a LOP network."""
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if not viewer:
        raise RuntimeError("No scene viewer found")
    available = viewer.hydraRenderers()
    match = next((name for name in available if name.lower() == renderer.lower()), None)
    if match is None:
        raise ValueError(f"Unknown viewport renderer: {renderer}. Use one of: {list(available)}")
    viewer.setHydraRenderer(match)
    return {"renderer": viewer.currentHydraRenderer()}


def frame_selection():
    """Frame the viewport on the current selection."""
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if not viewer:
        raise RuntimeError("No scene viewer found")
    viewport = viewer.curViewport()
    viewport.frameSelected()
    return {"framed": "selection"}


def frame_all():
    """Frame the viewport on all geometry."""
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if not viewer:
        raise RuntimeError("No scene viewer found")
    viewport = viewer.curViewport()
    viewport.frameAll()
    return {"framed": "all"}


def set_viewport_direction(direction):
    """Set viewport to a standard direction: front, back, left, right, top, bottom, persp."""
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if not viewer:
        raise RuntimeError("No scene viewer found")
    vtype = DIRECTIONS.get(direction)
    if vtype is None:
        raise ValueError(f"Unknown direction: {direction}. Use: {list(DIRECTIONS)}")
    viewer.curViewport().changeType(vtype)
    return {"direction": direction}


def set_current_network(path):
    """Set the current network path in the network editor."""
    editor = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
    if not editor:
        raise RuntimeError("No network editor found")
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    editor.setCurrentNode(node)
    return {"path": path}


# ---------------------------------------------------------------- capture


DIRECTIONS = {
    "front": hou.geometryViewportType.Front,
    "back": hou.geometryViewportType.Back,
    "left": hou.geometryViewportType.Left,
    "right": hou.geometryViewportType.Right,
    "top": hou.geometryViewportType.Top,
    "bottom": hou.geometryViewportType.Bottom,
    "persp": hou.geometryViewportType.Perspective,
}


@contextmanager
def kept_view(port):
    """Put the viewport back the way the user left it.

    A capture moves the view. The user is working in that same window, so every
    change here is undone when the picture is written, whatever happens.
    """
    kind = port.type()
    stash = port.defaultCamera().stash()
    camera = port.camera()
    try:
        yield
    finally:
        try:
            port.changeType(kind)
            if camera:
                port.setCamera(camera)
            else:
                port.setDefaultCamera(stash)
                port.useDefaultCamera()
        except hou.Error:
            pass


@contextmanager
def kept_display(node_path):
    """Show one node for the capture, and show the old one again after.

    Both flags move, not only the display flag: a viewport draws the display
    node, and a ROP draws the render node, so a picture of a node needs both.
    Looking at a node in the middle of a chain is a common question, and moving
    a flag by hand leaves the network of the user changed.
    """
    if not node_path:
        yield None
        return
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    before = {}
    for name, read in (("display", "displayNode"), ("render", "renderNode")):
        try:
            before[name] = getattr(node.parent(), read)()
        except AttributeError:
            before[name] = None
    try:
        node.setDisplayFlag(True)
        if hasattr(node, "setRenderFlag"):
            node.setRenderFlag(True)
    except (AttributeError, hou.PermissionError) as error:
        raise ValueError(f"{node_path} has no display flag to set: {error}")
    try:
        yield node
    finally:
        for name, old_node in before.items():
            if old_node is None or old_node == node:
                continue
            try:
                if name == "display":
                    old_node.setDisplayFlag(True)
                else:
                    old_node.setRenderFlag(True)
            except (hou.ObjectWasDeleted, hou.PermissionError, AttributeError):
                pass


def aim(port, target=None, look_from=None, radius=None):
    """Point the view at a place in the scene.

    target is what the view turns around. look_from is a position that says
    from where. radius is the distance between the two. Any of them alone is
    useful: target alone moves the pivot, radius alone comes closer.
    """
    camera = port.defaultCamera()
    if target is not None:
        camera.setPivot(hou.Vector3(target))
    if look_from is not None:
        to = hou.Vector3(target) if target is not None else camera.pivot()
        rotate = hou.hmath.buildRotateLookAt(hou.Vector3(look_from), to,
                                             hou.Vector3(0, 1, 0))
        camera.setRotation(rotate.extractRotationMatrix3())
        if radius is None:
            radius = (hou.Vector3(look_from) - to).length()
    if radius is not None:
        camera.setTranslation(hou.Vector3(0, 0, float(radius)))
        if camera.isOrthographic():
            camera.setOrthoWidth(float(radius))
    port.setDefaultCamera(camera)
    port.useDefaultCamera()


def fit(port, what, fill=0.9):
    """Frame the view on something, with room around it.

    `what` is "selection", "all", or the path of a node: the box of what that
    node cooked. fill is how much of the picture the thing takes; below 1 it
    leaves air around the subject, which is what makes a picture readable.
    """
    if not what:
        return None
    if what == "selection":
        port.frameSelected()
        return "selection"
    if what == "all":
        port.frameAll()
        return "all"
    node = hou.node(what)
    if not node:
        raise ValueError(f"frame: no node at {what}. Use 'selection', 'all', "
                         f"or the path of a node.")
    box = node.geometry().boundingBox() if hasattr(node, "geometry") else None
    if box is None or not box.isValid():
        raise ValueError(f"frame: {what} cooked no geometry to frame.")
    if fill and float(fill) != 1.0:
        # hou.BoundingBox cannot scale itself, so grow it around its centre.
        grow = (box.sizevec() * (1.0 / float(fill) - 1.0)) * 0.5
        box.setTo((*(box.minvec() - grow), *(box.maxvec() + grow)))
    port.frameBoundingBox(box)
    return what


def write_image(viewer, port, output=None, resolution=None, frames=None):
    """Write the viewport to a file, and confirm that the file is new.

    hou.GeometryViewport has no image export in 21.0 or 22.0, so this is a
    flipbook of one frame. An image left by an earlier call must not pass for
    this one, so the time of the file is read before and after.
    """
    if not output:
        output = new_file("mcp_viewport", ".png")
    output = os.path.abspath(output)
    folder = os.path.dirname(output)
    if folder:
        os.makedirs(folder, exist_ok=True)
    before = os.path.getmtime(output) if os.path.exists(output) else None

    start, end = frames if frames else (hou.frame(), hou.frame())
    settings = viewer.flipbookSettings().stash()
    settings.frameRange((start, end))
    settings.output(output)
    settings.outputToMPlay(False)
    if resolution:
        settings.useResolution(True)
        settings.resolution((int(resolution[0]), int(resolution[1])))
    viewer.flipbook(port, settings)
    if frames:
        return {"filepath": output, "frame_range": [start, end]}
    if not os.path.exists(output) or os.path.getmtime(output) == before:
        raise RuntimeError(f"The flipbook wrote no image at {output}")
    return {"filepath": output,
            "resolution": ([int(resolution[0]), int(resolution[1])] if resolution
                           else list(port.resolutionInPixels()))}


def new_file(stem, suffix):
    """A file name that no other capture writes over.

    Several captures in one batch would otherwise all write the same temporary
    file, and the caller would read the last one four times.
    """
    import tempfile
    import time
    return os.path.join(tempfile.gettempdir(),
                        f"{stem}_{time.strftime('%H%M%S')}_{int(time.time() * 1000) % 1000}{suffix}")


def _numbered(output, name):
    """A file name of its own for each view of a quad capture."""
    if not output:
        return new_file(f"mcp_viewport_{name}", ".png")
    root, ext = os.path.splitext(output)
    return f"{root}_{name}{ext or '.png'}"


def capture(mode="viewport", node=None, output=None, camera=None, direction=None,
            shading=None, renderer=None, frame=None, target=None, look_from=None,
            radius=None, fill=0.9, frame_range=None, frames=None, resolution=None):
    """One picture of the viewport, or four, with the view put back after.

    Every argument that moves the view is undone when the file is written, so
    a capture never leaves the window of the user somewhere else.
    """
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    if not viewer:
        raise RuntimeError("No scene viewer found")
    port = viewer.curViewport()
    aimed = target is not None or look_from is not None or radius is not None

    with kept_display(node), kept_view(port):
        if camera:
            set_viewport_camera(camera)
        if direction:
            set_viewport_direction(direction)
        if shading:
            set_viewport_display(shading_mode=shading)
        if renderer:
            set_viewport_renderer(renderer)
        # A node to look at is a node to frame, unless the caller aims by hand.
        framed = fit(port, frame or (None if aimed or not node else node), fill)
        if aimed:
            aim(port, target, look_from, radius)

        if mode == "flipbook":
            span = frame_range or (frames if isinstance(frames, (list, tuple))
                                   else list(hou.playbar.frameRange()))
            if not output:
                output = new_file("mcp_flipbook", ".$F4.jpg")
            report = write_image(viewer, port, output, resolution,
                                 frames=(float(span[0]), float(span[-1])))
        elif mode == "quad":
            images = []
            for name in ("top", "front", "right", "persp"):
                set_viewport_direction(name)
                fit(port, frame or (node or "all"), fill)
                shot = write_image(viewer, port, _numbered(output, name), resolution)
                images.append({"view": name, **shot})
            report = {"images": images, "filepath": images[-1]["filepath"]}
        else:
            report = write_image(viewer, port, output, resolution)
    report["framed"] = framed
    report["displayed"] = node
    return report


# A picture of the network editor is not possible, and this is the reason, so
# that nobody tries it again: every Houdini pane is a native GL drawable named
# RE_GLDrawable, not a QOpenGLWidget. QWidget.grab() draws nothing into it and
# gives a black image, and QScreen.grabWindow takes the pixels of the screen,
# which hold whatever window sits in front. Houdini 21.0 and 22.0 have no API
# that writes a pane to a file. Read the graph with node_inspect instead.
