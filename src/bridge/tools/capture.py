"""capture — look at the scene: a picture of the viewport, and the window state."""
import json
import os
from typing import Dict, List, Union

from mcp.server.mcpserver import Image

from ..connection import call

# A picture larger than this goes back as a path, because the message that
# holds it must stay small enough for the client to read.
MAX_INLINE_BYTES = 1_500_000


def tool(mode: str = "viewport", node: str = None, output: str = None,
         camera: str = None, direction: str = None, shading: str = None,
         renderer: str = None, frame: str = None,
         target: List[float] = None, look_from: List[float] = None,
         radius: float = None, fill: float = 0.9,
         frame_range: List[float] = None,
         frames: Union[float, List[float], Dict[str, float]] = None,
         resolution: List[int] = None, azimuth: float = None,
         elevation: float = None) -> list[Image | str]:
    """Make a picture of the scene and look at it.

    Use it to confirm your own work: numbers in a node do not tell you that the
    result looks wrong. Use it before you report that a task is done.

    Do not use it for a final picture: render does that through a ROP.

    The view goes back to where the user left it when the picture is written.
    Nothing here changes the scene for good.

    mode:
        "viewport" — the viewport as it is now.
        "quad"     — four pictures: top, front, right and perspective.
        "camera"   — through the camera node at `camera`.
        "flipbook" — a sequence over `frame_range` [start, end]. Returns the
                     path of the files, not a picture.

    A Houdini with no window has no viewport, and there an OpenGL ROP draws the
    same picture from the same arguments, with a camera and a ROP that the
    tool keeps for its next call.

    There is no picture of the network editor: every Houdini pane is a native
    GL drawable, and Qt draws nothing into it. Read the graph with node_inspect.

    node: the node to look at. Its display flag is set for the picture and the
    node that held the flag gets it back after. When the viewer shows another
    network, it shows the network of the node for the picture and goes back
    after. Without `frame` the view also frames that node.

    frames: one frame, a list, or {"start": 1, "end": 10, "step": 2}: one
    picture for each, and the playbar goes back after. A picture that holds
    only the background is an error, not a result.

    Aim the view with any of these:
        frame      — "selection", "all", or the path of a node: frame the view
                     on the box of what that node cooked.
        fill       — how much of the picture the framed thing takes. 0.9 leaves
                     air around it; 1.0 fills the frame.
        target     — [x, y, z] that the view turns around.
        look_from  — [x, y, z] that the view looks from.
        radius     — the distance between the two.
        direction  — "top", "front", "left", "right", "back", "bottom",
                     "persp".
        azimuth    — turn the view around what it frames, in degrees around
                     the up axis; with `elevation`, the degrees above the
                     ground. 0 and 0 look from the front; azimuth 45 and
                     elevation 30 give a three-quarter view. Nothing is added
                     to the scene.
        camera     — look through this camera node.
        shading    — "smooth", "smooth_wire", "flat", "wireframe".
        renderer   — the Hydra renderer of a viewer on a LOP network, for
                     example "Karma CPU". An unknown name lists the ones
                     available.

    output: where to write the file. Without it, Houdini writes to a temporary
    file. resolution is [width, height]; the height follows the shape of
    the viewport, so the picture is not stretched.

    Returns the picture, plus JSON with the state of the window: the frame, the
    open file, the selection, the network in front, and which nodes carry the
    display, the render and the template flag. A picture that does not change
    after an edit is almost always a display flag on another node.

    Houdini without a GUI has no viewport: then the result says so and names
    the next action.
    """
    result = call("capture", {"mode": mode, "node": node, "output": output,
                              "camera": camera, "direction": direction,
                              "shading": shading, "renderer": renderer,
                              "frame": frame, "target": target,
                              "look_from": look_from, "radius": radius,
                              "fill": fill, "frame_range": frame_range,
                              "frames": frames, "resolution": resolution,
                              "azimuth": azimuth, "elevation": elevation},
                  timeout=300.0)

    contents = []
    if mode != "flipbook":
        for path in _paths(result):
            contents.append(_picture(path, result))
    return [item for item in contents if item is not None] + \
           [json.dumps(result, indent=2, default=str)]


def _paths(result) -> list:
    """Every file the capture wrote. A quad capture writes four."""
    images = result.get("images")
    if images:
        return [image.get("filepath") for image in images if image.get("filepath")]
    one = result.get("filepath") or result.get("path")
    return [one] if one else []


def _picture(path, result):
    """The image itself when this machine can read it and it is small enough."""
    if not os.path.exists(path):
        result.setdefault("not_inline", []).append(
            f"Houdini wrote {path}, and this machine cannot see it. "
            f"Houdini runs somewhere else.")
        return None
    size = os.path.getsize(path)
    if size > MAX_INLINE_BYTES:
        result.setdefault("not_inline", []).append(
            f"{path} is {size} bytes. Read it yourself, or capture a smaller "
            f"one with resolution=[800, 450].")
        return None
    return Image(path=path)
