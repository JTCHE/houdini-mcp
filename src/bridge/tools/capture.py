"""capture — look at the scene: a picture of the viewport, and the window state."""
import json
import os
from typing import Dict, List, Union

from mcp.server.mcpserver import Image

from mcp.types import ToolAnnotations

from ..connection import call

# The view, the flags and the playbar go back after the picture. Only the
# picture file is written.
ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True,
                              openWorldHint=False)

PARAMS = {
    "mode": 'One of "viewport", "quad", "camera", "flipbook", "sheet", "movie".',
    "node": "The node to look at. It gets the display flag for the picture, and the flag "
            "goes back after. The viewer shows its network, and goes back after. Without "
            "`frame`, the view also frames it.",
    "output": "The file to write. Without it, a temporary file.",
    "camera": "camera mode: the camera node to look through. On a LOP network with "
              "`renderer`, a USD camera prim.",
    "direction": 'The view axis: "top", "front", "left", "right", "back", "bottom" or '
                 '"persp".',
    "shading": 'One of "smooth", "smooth_wire", "flat", "wireframe".',
    "renderer": 'The Hydra renderer of a viewer on a LOP network, for example "Karma CPU". '
                "An unknown name lists the ones available.",
    "frame": 'What to frame the view on: "selection", "all", or a node path (the box of '
             "what that node cooked).",
    "target": "[x, y, z]: the point that the view turns around.",
    "look_from": "[x, y, z]: the point that the view looks from.",
    "radius": "The distance between target and look_from.",
    "fill": "How much of the picture the framed thing takes: 0.9 leaves air around it, "
            "1.0 fills it.",
    "frame_range": "flipbook and movie: [start, end].",
    "frames": 'One frame, a list, or {"start": 1, "end": 10, "step": 2}: one picture for '
              "each. sheet: the frames of the tiles. The playbar goes back after. A picture "
              "that holds only the background is an error.",
    "resolution": "[width, height] in pixels. The height follows the shape of the viewport, "
                  "so the picture is not stretched.",
    "azimuth": "Degrees around the up axis, around what the view frames. 0 looks from the "
               "front. Nothing is added to the scene.",
    "elevation": "Degrees above the ground, with azimuth. 30 with azimuth 45 is a "
                 "three-quarter view.",
    "start": "sheet: the first frame. Without it, the current frame.",
    "step": "sheet: the frames between tiles. Over 2 hides movement and gives a warning.",
    "count": "sheet: how many tiles, when frames is not given.",
    "columns": "sheet: tiles in each row.",
    "tile_width": "sheet: the width of each tile in pixels.",
    "background": "sheet and movie: the grey of the background, 0-255. Smoke reads best on "
                  "mid grey.",
    "reference": "sheet: a picture file to put in the first tile, to compare.",
    "color_by": "sheet and movie: colour the points by this attribute, blue at the low end "
                "of color_range and red at the high end. A vector uses its length.",
    "color_range": "[low, high] for color_by. Without it, [0, 1].",
    "fps": "movie: frames per second.",
    "contour": "sheet: a step. Colour by the fraction of the value over the step, so the "
               "lines of equal value show, for example the shells of a distance field.",
    "slab": '[axis, thickness], for example ["z", 0.1]: draw only the points in a thin cut '
            "through the middle, so the inside of a solid cloud shows.",
    "vectors": "sheet: a scale. Draw a line along the color_by vector from up to about 3000 "
               "points. An empty result is an error.",
    "settle": "Seconds that a renderer such as Karma draws before each picture. Karma "
              "starts from noise: 20 to 30 gives a clean frame. With frames or in flipbook "
              "mode it renders a sequence through the viewport, with no husk and no render "
              "license.",
}

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
         elevation: float = None, start: float = None, step: float = 1,
         count: int = 12, columns: int = None, tile_width: int = 320,
         background: int = 96, reference: str = None, color_by: str = None,
         color_range: List[float] = None, fps: float = 24, contour: float = None,
         slab: List[Union[str, float]] = None,
         vectors: float = None, settle: float = None) -> list[Image | str]:
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
        "sheet"    — `node` at many frames on one picture, a tile for each
                     frame with its number, all from one camera that does not
                     move. Frames: `frames`, or `count` frames from `start`
                     (the current frame) at `step` (1). A step over 2 hides
                     movement and gives a warning: look at a short range at
                     step 1. `reference` is a picture to put first, to
                     compare. `columns`, `tile_width` set the grid. The
                     frames cook in order, forward, and the result gives
                     the cook seconds of each one.
        "movie"    — `node` over `frames` or `frame_range` (the playbar
                     range) as an MP4 at `fps`, `resolution` [width] wide.
                     Returns the path; open it in a player.
        Both draw with an OpenGL ROP, with or without a window, over a flat
        grey `background`. To see where a point attribute lives, use
        "sheet" with one frame and `color_by`, with `contour`, `slab` or
        `vectors`.

    A Houdini with no window has no viewport, and there an OpenGL ROP draws the
    same picture from the same arguments over a grey background. It runs in a
    new hython, so the scene gets no camera and no ROP.

    There is no picture of the network editor: every Houdini pane is a native
    GL drawable, and Qt draws nothing into it. Read the graph with node_inspect.

    Aim the view with `frame` and `fill`, with `target`, `look_from` and
    `radius`, with `direction`, with `azimuth` and `elevation`, or with
    `camera`.

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
                              "azimuth": azimuth, "elevation": elevation,
                              "start": start, "step": step, "count": count,
                              "columns": columns, "tile_width": tile_width,
                              "background": background, "reference": reference,
                              "color_by": color_by, "color_range": color_range,
                              "fps": fps, "contour": contour, "slab": slab,
                              "vectors": vectors, "settle": settle},
                  timeout=300.0 + (settle or 0) * 1.5 * _count(frames))

    contents = []
    if mode not in ("flipbook", "movie"):
        for path in _paths(result):
            contents.append(_picture(path, result))
    return [item for item in contents if item is not None] + \
           [json.dumps(result, separators=(",", ":"), default=str)]


def _count(frames) -> int:
    """How many pictures `frames` asks for, to size the wait."""
    if isinstance(frames, list):
        return len(frames)
    if isinstance(frames, dict):
        step = abs(float(frames.get("step") or 1))
        return int(abs(float(frames.get("end", frames["start"])) - float(frames["start"]))
                   / step) + 1
    return 1


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
