"""capture — look at the scene: a picture of the viewport, and the window state."""
import json
import os
from typing import List

from mcp.server.mcpserver import Image

from ..connection import call

# A picture larger than this goes back as a path, because the message that
# holds it must stay small enough for the client to read.
MAX_INLINE_BYTES = 1_500_000


def tool(mode: str = "viewport", output: str = None, camera: str = None,
         direction: str = None, shading: str = None, renderer: str = None,
         frame: str = None, orthographic: bool = False,
         render_engine: str = "opengl", frame_range: List[float] = None,
         resolution: List[int] = None) -> list[Image | str]:
    """Make a picture of the scene and look at it.

    Use it to confirm your own work: numbers in a node do not tell you that
    the result looks wrong. Use it before you report that a task is done.

    Do not use it for a final picture: render does that through a ROP.

    mode:
        "viewport" — the viewport as it is now.
        "quad"     — four views: top, front, side and perspective.
        "camera"   — through the camera node at `camera`.
        "flipbook" — a sequence over `frame_range` [start, end]. `resolution`
                     is [width, height]. Returns the path, not a picture.

    Before the capture, these change the view when you give them: `camera`,
    `direction` ("top", "front", "persp", …), `shading` ("smooth",
    "smooth_wire", "flat", "wireframe"), `renderer` (the Hydra renderer of a
    viewer on a LOP network, for example "Karma CPU"; an unknown name lists
    the ones available), and `frame` ("selection" or "all") to fit the view
    around the geometry.

    output: where to write the file. Without it, Houdini writes to a temporary
    file.

    Returns the picture, plus JSON with the state of the window: the frame, the
    open file, the selection and the network in front. Houdini without a GUI
    has no viewport: then the result says so and names the next action.
    """
    result = call("capture", {"mode": mode, "output": output, "camera": camera,
                              "direction": direction, "shading": shading,
                              "renderer": renderer, "frame": frame,
                              "orthographic": orthographic,
                              "render_engine": render_engine,
                              "frame_range": frame_range,
                              "resolution": resolution}, timeout=300.0)

    path = result.get("filepath") or result.get("path")
    contents = []
    if path and os.path.exists(path):
        size = os.path.getsize(path)
        if size <= MAX_INLINE_BYTES and mode != "flipbook":
            contents.append(Image(path=path))
        else:
            result["not_inline"] = (f"The file is {size} bytes. Read {path} "
                                    "yourself, or capture a smaller one.")
    elif path:
        result["not_inline"] = (f"Houdini wrote {path}, and this machine cannot "
                                "see it. Houdini runs somewhere else.")
    contents.append(json.dumps(result, indent=2, default=str))
    return contents
