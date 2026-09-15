"""Make a picture of the scene, and say what the window shows.

Without a GUI there is no viewport. Then an OpenGL ROP draws the same picture,
so the same call answers in hython and in a Houdini with a window.
"""
import hou

from . import unknown_mode
from ..handlers import offscreen, viewport

MUTATES = True  # a capture moves the view, and puts it back after

MODES = ("viewport", "quad", "camera", "flipbook")


def run(mode="viewport", node=None, output=None, camera=None, direction=None,
        shading=None, renderer=None, frame=None, target=None, look_from=None,
        radius=None, fill=0.9, frame_range=None, frames=None,
        resolution=None):
    if mode not in MODES:
        raise unknown_mode(mode, MODES)
    if not hou.isUIAvailable():
        # No window, so no viewport. An OpenGL ROP draws without one, and the
        # arguments mean the same thing, so the caller writes the same call.
        result = offscreen.capture(
            node_path=node, output=output, frames=_span(frames, frame_range),
            resolution=resolution, camera=camera, direction=direction or "persp",
            target=target, look_from=look_from, radius=radius, fill=fill,
            shading=shading)
        return {**result, "window_state": _state()}

    if mode == "flipbook" and not (frames or frame_range):
        frame_range = list(hou.playbar.frameRange())
    if mode == "camera" and not camera:
        raise ValueError("mode 'camera' needs the path of a camera node.")
    result = viewport.capture(
        mode=mode, node=node, output=output, camera=camera,
        direction=direction, shading=shading, renderer=renderer, frame=frame,
        target=target, look_from=look_from, radius=radius, fill=fill,
        frame_range=frame_range, frames=frames, resolution=resolution)
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
