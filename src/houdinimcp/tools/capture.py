"""Make a picture of the scene, and say what the window shows.

Without a GUI there is no viewport. Then an OpenGL ROP draws the same picture,
so the same call answers in hython and in a Houdini with a window.
"""
import hou

from . import unknown_mode
from ..handlers import offscreen, sheets, viewport

MUTATES = True  # a capture moves the view, and puts it back after

MODES = ("viewport", "quad", "camera", "flipbook", "sheet", "movie")


def run(mode="viewport", node=None, output=None, camera=None, direction=None,
        shading=None, renderer=None, frame=None, target=None, look_from=None,
        radius=None, fill=0.9, frame_range=None, frames=None,
        resolution=None, azimuth=None, elevation=None, start=None, step=1,
        count=12, columns=None, tile_width=320, background=96, reference=None,
        color_by=None, color_range=None, fps=24, contour=None, slab=None,
        vectors=None, settle=None):
    if mode not in MODES:
        raise unknown_mode(mode, MODES)
    if mode in ("sheet", "movie"):
        # An OpenGL ROP draws these with or without a window, so the call is
        # the same in both.
        if not node:
            raise ValueError(f"mode '{mode}' needs `node`.")
        shared = dict(node_path=node, background=background, azimuth=azimuth,
                      elevation=elevation, fill=fill, color_by=color_by,
                      color_range=color_range, contour=contour, slab=slab,
                      vectors=vectors, output=output, direction=direction,
                      target=target, look_from=look_from, radius=radius)
        if mode == "sheet":
            return sheets.sheet(frames=frames, start=start, step=step, count=count,
                                columns=columns, tile_width=tile_width,
                                reference=reference, **shared)
        return sheets.movie(frames=_span(frames, frame_range), fps=fps,
                            width=(resolution or [640])[0], **shared)
    if not hou.isUIAvailable():
        # No window, so no viewport. An OpenGL ROP draws without one, and the
        # arguments mean the same thing, so the caller writes the same call.
        shared = dict(node_path=node, frames=_span(frames, frame_range),
                      resolution=resolution, camera=camera, target=target,
                      look_from=look_from, radius=radius, fill=fill, shading=shading,
                      azimuth=azimuth, elevation=elevation)
        if mode == "quad":
            images = []
            for name in ("top", "front", "right", "persp"):
                try:
                    images.append({"view": name, **offscreen.capture(
                        output=viewport._numbered(output, name), direction=name, **shared)})
                except offscreen.Empty as error:
                    # A flat thing seen from its edge draws nothing, and the
                    # other views still show it.
                    images.append({"view": name, "empty": str(error)})
            drawn = [image for image in images if "filepath" in image]
            if not drawn:
                raise offscreen.Empty("The OpenGL ROP drew nothing from any of the four "
                                      "views. The geometry is empty.")
            result = {"images": images, "filepath": drawn[-1]["filepath"]}
        else:
            result = offscreen.capture(output=output, direction=direction or "persp", **shared)
        return {**result, "window_state": _state()}

    if mode == "flipbook" and not (frames or frame_range):
        frame_range = list(hou.playbar.frameRange())
    if mode == "camera" and not camera:
        raise ValueError("mode 'camera' needs the path of a camera node.")
    return _with_state(viewport.capture(
        mode=mode, node=node, output=output, camera=camera,
        direction=direction, shading=shading, renderer=renderer, frame=frame,
        target=target, look_from=look_from, radius=radius, fill=fill,
        frame_range=frame_range, frames=frames, resolution=resolution,
        azimuth=azimuth, elevation=elevation, settle=settle))


def _with_state(capture):
    """A viewport capture waits in the event loop (see server._step), so the
    state of the window is read when it ends."""
    result = yield from capture
    return {**result, "window_state": _state()}


def _span(frames, frame_range):
    """The frames to draw: a list, a number, or the range between two numbers."""
    if frames is not None:
        return frames
    if frame_range:
        return {"start": frame_range[0], "end": frame_range[-1]}
    return None


def _state():
    """What the session shows now: frame, selection, the network in front, and
    which nodes carry the display, the render and the template flag."""
    state = {"frame": hou.frame(), "hip_file": hou.hipFile.path(),
             "selected": [node.path() for node in hou.selectedNodes()],
             "ui_available": hou.isUIAvailable()}
    if not hou.isUIAvailable():
        return state
    editor = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
    state["network"] = editor.pwd().path() if editor else None
    try:
        state["viewport"] = viewport.get_viewport_info()
    except Exception as error:
        state["viewport"] = f"unavailable: {error}"
    viewer = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)
    state["flags"] = _flags(viewer.pwd() if viewer else
                            (editor.pwd() if editor else None))
    return state


def _flags(network):
    """Which node the picture actually shows.

    A picture that does not change after an edit is almost always a display
    flag on another node, so the answer names the flagged nodes every time.
    """
    if not network:
        return None
    found = {"network": network.path()}
    for name, read in (("display", "displayNode"), ("render", "renderNode")):
        try:
            node = getattr(network, read)()
        except AttributeError:
            continue
        found[name] = node.path() if node else None
    # At object level no single node carries the flag: each object carries its
    # own, and an object that is off is why the picture is empty.
    if "display" not in found:
        found["displayed"] = _flagged(network, "isDisplayFlagSet")
    found["template"] = _flagged(network, "isTemplateFlagSet")
    return found


def _flagged(network, test):
    """The children of a network whose flag is on."""
    on = []
    for child in network.children():
        try:
            if getattr(child, test)():
                on.append(child.path())
        except AttributeError:
            continue
    return on
