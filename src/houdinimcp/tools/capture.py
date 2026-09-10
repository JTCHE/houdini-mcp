"""Make a picture of the scene, and say what the window shows.

Without a GUI there is no viewport. Then this returns the window state and says
so, and the caller must render a camera through a ROP instead.
"""
import hou

from . import unknown_mode
from ..handlers import rendering, viewport

MUTATES = True  # a capture can change the view, the camera and the shading

MODES = ("viewport", "quad", "camera", "flipbook")


def run(mode="viewport", output=None, camera=None, direction=None, shading=None,
        renderer=None, frame=None, orthographic=False, render_engine="opengl",
        frame_range=None, resolution=None):
    if not hou.isUIAvailable():
        return {"image": None,
                "reason": "This Houdini has no GUI, so it has no viewport to capture. "
                          "Build a camera and a ROP, then use the render tool.",
                "window_state": _state()}

    if camera and mode == "viewport":
        viewport.set_viewport_camera(camera)
    if direction:
        viewport.set_viewport_direction(direction)
    if shading:
        viewport.set_viewport_display(shading_mode=shading)
    if renderer:
        viewport.set_viewport_renderer(renderer)
    if frame == "selection":
        viewport.frame_selection()
    elif frame == "all":
        viewport.frame_all()

    if mode == "viewport":
        result = viewport.capture_screenshot(output)
    elif mode == "quad":
        result = rendering.handle_render_quad_view(orthographic, output, render_engine)
    elif mode == "camera":
        if not camera:
            raise ValueError("mode 'camera' needs the path of a camera node.")
        result = rendering.handle_render_specific_camera(camera, output, render_engine)
    elif mode == "flipbook":
        result = rendering.render_flipbook(frame_range, output, resolution)
    else:
        raise unknown_mode(mode, MODES)
    return {**result, "window_state": _state()}


def _state():
    """What the session shows now: frame, selection, and the network in front."""
    state = {"frame": hou.frame(), "hip_file": hou.hipFile.path(),
             "selected": [node.path() for node in hou.selectedNodes()],
             "ui_available": hou.isUIAvailable()}
    if hou.isUIAvailable():
        editor = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
        state["network"] = editor.pwd().path() if editor else None
        try:
            state["viewport"] = viewport.get_viewport_info()
        except Exception as error:
            state["viewport"] = f"unavailable: {error}"
    return state
