"""Pictures over time: a contact sheet of frames, and a movie.

One still cannot show a fault that lives in time, and a sheet at a wide step
cannot either: each tile is another picture, and the eye has nothing to
follow. So the step is 1 by default, and a step over 2 gives a warning.

All frames come from one camera that does not move: a camera that frames each
frame on its own centres the subject every time, and all travel disappears.
"""
import math
import os
import subprocess

import hou

from . import offscreen, timing, viewport

SLOW_STEP = 2


def _render(node_path, wanted, size, azimuth, elevation, fill, **look):
    node = hou.node(node_path)
    if node is None:
        raise ValueError(f"Node not found: {node_path}")
    box = hou.BoundingBox()
    with timing.keep_frame():
        for frame in (wanted[0], wanted[len(wanted) // 2], wanted[-1]):
            hou.setFrame(frame)
            box.enlargeToContain(offscreen._placed(node).boundingBox())
    if not box.isValid():
        raise ValueError(f"{node_path} cooked no geometry at frames {wanted[0]:g} to "
                         f"{wanted[-1]:g}.")
    direction = offscreen._orbit_direction(azimuth, elevation) \
        if azimuth is not None or elevation is not None else "persp"
    view, _ = offscreen._aim(box, direction, fill=fill)
    return offscreen.draw([node], view, wanted, size, **look)


def _label(image, text):
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 8 + 7 * len(text), 16), fill=(0, 0, 0))
    draw.text((4, 2), text, fill=(255, 255, 255))


def sheet(node_path, frames=None, start=None, step=1, count=12, columns=None,
          tile_width=320, background=96, reference=None, azimuth=None, elevation=None,
          fill=0.9, output=None, **look):
    """A contact sheet: the node at each frame, in a grid, with the frame
    number on each tile, and a reference picture first when one is given."""
    from PIL import Image
    wanted = timing.frame_list(frames) if frames is not None else \
        [float(start if start is not None else hou.frame()) + float(step or 1) * index
         for index in range(int(count or 12))]
    size = (int(tile_width), int(tile_width) * 3 // 4)
    tiles = []
    if reference:
        if not os.path.isfile(reference):
            raise ValueError(f"There is no reference picture at {reference}.")
        picture = Image.open(reference).convert("RGB")
        picture.thumbnail(size)
        tile = Image.new("RGB", size, (background,) * 3)
        tile.paste(picture, ((size[0] - picture.width) // 2, (size[1] - picture.height) // 2))
        _label(tile, "reference")
        tiles.append(tile)
    for frame, path in zip(wanted, _render(node_path, wanted, size, azimuth, elevation,
                                            fill, **look)):
        tile = offscreen.over_grey(path, background)
        _label(tile, f"{frame:g}")
        tiles.append(tile)

    columns = int(columns or math.ceil(math.sqrt(len(tiles))))
    rows = math.ceil(len(tiles) / columns)
    board = Image.new("RGB", (columns * size[0], rows * size[1]), (background,) * 3)
    for index, tile in enumerate(tiles):
        board.paste(tile, ((index % columns) * size[0], (index // columns) * size[1]))
    output = os.path.abspath(output or viewport.new_file("mcp_sheet", ".png"))
    board.save(output)
    report = {"filepath": output, "frames": wanted, "columns": columns, "tile": list(size)}
    steps = [b - a for a, b in zip(wanted, wanted[1:])]
    if steps and max(steps) > SLOW_STEP:
        report["warning"] = (f"The step is {max(steps):g} frames. Past {SLOW_STEP}, each tile "
                             f"is another picture and movement cannot be read. Use a short "
                             f"range at step 1.")
    return report


def movie(node_path, frames=None, fps=24, width=640, background=96, azimuth=None,
          elevation=None, fill=0.9, output=None, **look):
    """An MP4 of the node over the frames, or over the playbar range."""
    if frames is None:
        first, last = hou.playbar.frameRange()[:2]
        frames = {"start": first, "end": last}
    wanted = timing.frame_list(frames)
    # The encoder refuses an odd width or height.
    size = (int(width) // 2 * 2, int(width) * 3 // 4 // 2 * 2)
    drawn = _render(node_path, wanted, size, azimuth, elevation, fill, **look)
    folder = os.path.dirname(drawn[0])
    for index, (frame, path) in enumerate(zip(wanted, drawn)):
        tile = offscreen.over_grey(path, background)
        _label(tile, f"{frame:g}")
        tile.save(os.path.join(folder, f"movie.{index:05d}.png"))
    output = os.path.abspath(output or viewport.new_file("mcp_movie", ".mp4"))
    result = subprocess.run(
        [_encoder(), "-y", "-loglevel", "error", "-framerate", str(fps),
         "-i", os.path.join(folder, "movie.%05d.png"), "-c:v", "libopenh264",
         "-pix_fmt", "yuv420p", output], capture_output=True, text=True)
    if result.returncode != 0 or not os.path.isfile(output):
        raise RuntimeError(f"The encoder failed: {result.stderr.strip()[-600:]}")
    return {"filepath": output, "frames": len(wanted), "first": wanted[0],
            "last": wanted[-1], "fps": fps, "size": list(size)}


def _encoder():
    """The ffmpeg that ships with Houdini. It has libopenh264, not libx264."""
    shipped = os.path.join(hou.getenv("HFS"), "bin",
                           "hffmpeg.exe" if os.name == "nt" else "hffmpeg")
    if not os.path.isfile(shipped):
        raise RuntimeError(f"There is no hffmpeg at {shipped}.")
    return shipped
