"""Pictures drawn by an OpenGL ROP, with or without a window.

hython has no viewport, and that is where most agent work happens. An OpenGL
ROP draws without one. hython 22.0 stops with a segmentation fault on the
second OpenGL ROP render in one process, so the ROP never runs in the session:
the session writes the geometry of each frame to disk, and a new hython
(gl_child.py) draws all the frames in one render. The scene of the user gets
no camera and no ROP from this.
"""
import json
import math
import os
import subprocess

import hou

from . import timing, viewport


class Empty(RuntimeError):
    """The picture holds only the background."""


# The lens of a new Houdini camera: the one gl_child draws with.
FOCAL, APERTURE = 50.0, 41.4214
SHADING = {"smooth": "smooth", "smooth_wire": "smoothwire", "flat": "flat",
           "wireframe": "wire"}

# Where the camera sits, as a direction from the middle of what it looks at.
DIRECTIONS = {
    "persp": (1.0, 0.6, 1.0),
    "front": (0.0, 0.0, 1.0),
    "back": (0.0, 0.0, -1.0),
    "right": (1.0, 0.0, 0.0),
    "left": (-1.0, 0.0, 0.0),
    "top": (0.0, 1.0, 0.0),
    "bottom": (0.0, -1.0, 0.0),
}


def _box(node):
    """The box of what a node cooked, or of everything that is displayed."""
    if node is not None:
        return _geometry(node).boundingBox()
    box = hou.BoundingBox()
    for child in _displayed():
        box.enlargeToContain(_placed(child).boundingBox())
    return box


def _displayed():
    """The SOP that each displayed geometry object of /obj shows. A camera or
    a light has a display SOP too: its guide."""
    return [child.displayNode() for child in hou.node("/obj").children()
            if child.type().name() == "geo" and child.isObjectDisplayed()
            and child.displayNode() is not None]


def _geometry(node):
    geometry = node.geometry() if hasattr(node, "geometry") else None
    if geometry is None:
        errors = "; ".join(node.errors()) if hasattr(node, "errors") else ""
        raise ValueError(f"{node.path()} has no geometry to draw"
                         + (f": {errors}" if errors else ". The OpenGL ROP draws SOP "
                            "geometry; give a SOP."))
    return geometry


def _placed(node):
    """The geometry of a SOP where its object puts it in the world."""
    geometry = hou.Geometry()
    geometry.merge(_geometry(node))
    owner = node
    while owner is not None and not isinstance(owner, hou.ObjNode):
        owner = owner.parent()
    if owner is not None:
        geometry.transform(owner.worldTransform())
    return geometry


def _orbit_direction(azimuth, elevation):
    """The direction from the target to the eye for an orbit angle in degrees.
    0 and 0 look along -Z, from the front, as in the viewport."""
    turn, lift = math.radians(azimuth or 0.0), math.radians(elevation or 0.0)
    return (math.sin(turn) * math.cos(lift), math.sin(lift),
            math.cos(turn) * math.cos(lift))


def _aim(box, direction="persp", target=None, look_from=None, radius=None, fill=0.9,
         aspect=0.75):
    """A view that sees the box, with room around it. `direction` is a name,
    or a direction vector from the target to the eye. `aspect` is the height
    of the picture over its width."""
    middle = hou.Vector3(target) if target is not None else box.center()
    if look_from is not None:
        where = hou.Vector3(look_from)
    else:
        size = box.sizevec().length() or 1.0
        # The aperture is the width. A wide picture sees less in height.
        half = APERTURE / (2.0 * FOCAL) * min(1.0, float(aspect))
        away = radius if radius is not None else (size * 0.5) / (half * float(fill or 1.0))
        offset = hou.Vector3(direction if isinstance(direction, tuple)
                             else DIRECTIONS.get(direction, DIRECTIONS["persp"])).normalized()
        where = middle + offset * away
    # A view along the up axis has no roll to take from it, and the look-at
    # fails. Then -Z is up, as in the top view of Houdini.
    down = (where - middle).normalized()[1]
    up = hou.Vector3(0, 1, 0) if abs(down) < 0.999 else hou.Vector3(0, 0, -1 if down > 0 else 1)
    look = hou.hmath.buildRotateLookAt(where, middle, up)
    view = _view(where, look.extractRotates(), FOCAL, APERTURE, "perspective", 1.0)
    return view, {"look_from": list(where), "target": list(middle)}


def _view(translate, rotate, focal, aperture, projection, orthowidth):
    return {"tx": translate[0], "ty": translate[1], "tz": translate[2],
            "rx": rotate[0], "ry": rotate[1], "rz": rotate[2], "focal": focal,
            "aperture": aperture, "projection": projection, "orthowidth": orthowidth}


def _camera_view(camera):
    """The view through a camera node of the scene at the current frame."""
    parts = camera.worldTransform().explode()
    return _view(parts["translate"], parts["rotate"], camera.evalParm("focal"),
                 camera.evalParm("aperture"), camera.parm("projection").evalAsString(),
                 camera.evalParm("orthowidth"))


def draw(sources, view, frames, size, shading=None, color_by=None, color_range=None,
         contour=None, slab=None, vectors=None):
    """Draw SOP nodes at each frame, and return one PNG with alpha per frame.

    `view` is a view from _aim, or a camera node read at each frame. `slab`
    is [axis, thickness]: only the points in that cut through the middle.
    `contour` is a step: colour by the fraction of the value over it.
    `vectors` is a scale: a line along the vector `color_by` from the points.
    """
    if (contour or vectors) and not color_by:
        raise ValueError("contour and vectors read the attribute that color_by names.")
    if slab is not None and (len(slab) != 2 or str(slab[0]) not in ("x", "y", "z")
                             or float(slab[1]) <= 0):
        raise ValueError(f"slab is [axis, thickness], for example ['z', 0.1], not {slab}.")
    if shading is not None and shading not in SHADING:
        raise ValueError(f"Unknown shading: {shading}. Use: {list(SHADING)}")
    if not sources:
        raise ValueError("Nothing is displayed in /obj, so there is nothing to draw.")
    color_size = None
    if color_by:
        for node in sources:
            attrib = _geometry(node).findPointAttrib(color_by)
            if attrib is None or attrib.dataType() != hou.attribData.Float \
                    or attrib.size() > 4:
                names = [attrib.name() for attrib in _geometry(node).pointAttribs()]
                raise ValueError(f"{node.path()} has no float point attribute "
                                 f"'{color_by}' of 1 to 4 values. Point attributes: {names}")
            color_size = attrib.size()
            if vectors and color_size != 3:
                raise ValueError(f"vectors needs a vector attribute, and '{color_by}' has "
                                 f"{color_size} values.")
    folder = viewport.new_file("mcp_draw", "")
    os.makedirs(folder)
    views = []
    with timing.keep_frame():
        for index, frame in enumerate(frames, 1):
            hou.setFrame(frame)
            for number, node in enumerate(sources):
                _placed(node).saveToFile(os.path.join(folder, f"s{number}.{index}.bgeo.sc"))
            views.append(_camera_view(view) if isinstance(view, hou.ObjNode) else view)
    picture = os.path.join(folder, "draw.$F4.png").replace("\\", "/")
    job = {"sources": [os.path.join(folder, f"s{number}.$F.bgeo.sc").replace("\\", "/")
                       for number in range(len(sources))],
           "views": views, "count": len(frames), "size": [int(size[0]), int(size[1])],
           "shading": SHADING[shading or "smooth"], "picture": picture,
           "color_by": color_by, "color_size": color_size, "color_range": color_range,
           "contour": contour, "slab": slab, "vectors": vectors}
    with open(os.path.join(folder, "job.json"), "w") as handle:
        json.dump(job, handle)
    hython = os.path.join(hou.getenv("HFS"), "bin", "hython.exe" if os.name == "nt" else "hython")
    # The child draws with OpenGL only. An OpenFX plug-in of the system can
    # crash it as it loads: hython 20.5 started from a session stopped with an
    # access violation in the DLL init of a CUDA plug-in.
    environment = {key: value for key, value in os.environ.items() if key != "OFX_PLUGIN_PATH"}
    environment["HOUDINI_DISABLE_OPENFX_DEFAULT_PATH"] = "1"
    result = subprocess.run([hython, os.path.join(os.path.dirname(os.path.dirname(__file__)), "gl_child.py"),
                             os.path.join(folder, "job.json")],
                            capture_output=True, text=True, timeout=600, env=environment,
                            # Houdini has no console, so Windows gives hython a new one on top.
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    written = [hou.text.expandStringAtFrame(picture, index)
               for index in range(1, len(frames) + 1)]
    missing = [path for path in written if not os.path.isfile(path)]
    if result.returncode != 0 or missing:
        raise RuntimeError(f"The OpenGL ROP drew {len(written) - len(missing)} of "
                           f"{len(written)} frames, and hython stopped with code "
                           f"{result.returncode & 0xFFFFFFFF:#x}. hython said: "
                           f"{(result.stderr or result.stdout).strip()[-800:]}")
    if all(_empty(path) for path in written):
        raise Empty(f"The OpenGL ROP drew nothing at any of the {len(written)} frames. "
                           f"The geometry is outside the view, or it is empty.")
    return written


def _empty(path):
    """True when no pixel of the picture is drawn: its alpha is zero."""
    from PIL import Image
    return Image.open(path).convert("RGBA").getchannel("A").getbbox() is None


def over_grey(path, background=96):
    """A frame over a flat grey, as an RGB image. The ROP writes straight
    alpha, and a mid grey shows the density of smoke best."""
    from PIL import Image
    frame = Image.open(path).convert("RGBA")
    ground = Image.new("RGBA", frame.size, (background, background, background, 255))
    return Image.alpha_composite(ground, frame).convert("RGB")


def capture(node_path=None, output=None, frames=None, resolution=None,
            camera=None, direction="persp", target=None, look_from=None,
            radius=None, fill=0.9, shading=None, azimuth=None, elevation=None):
    """Draw a node, or everything displayed in /obj, at one frame or at several.

    Give `camera` to look through a camera of the scene.
    """
    node = None
    if node_path:
        node = hou.node(node_path)
        if not node:
            raise ValueError(f"Node not found: {node_path}")

    wanted = timing.frame_list(frames, default=[hou.frame()])
    size = [int(value) for value in resolution or (1280, 720)]
    if len(size) == 1:
        size.append(size[0] * 9 // 16)
    aimed = None
    if camera:
        view = hou.node(camera)
        if not isinstance(view, hou.ObjNode) or view.parm("focal") is None:
            raise ValueError(f"Camera not found: {camera}")
    else:
        if azimuth is not None or elevation is not None:
            direction = _orbit_direction(azimuth, elevation)
        view, aimed = _aim(_box(node), direction, target, look_from, radius, fill,
                           size[1] / size[0])

    drawn = draw([node] if node is not None else _displayed(), view, wanted, size, shading)
    if not output:
        output = viewport.new_file("mcp_offscreen", ".$F4.png" if len(wanted) > 1 else ".png")
    output = os.path.abspath(output)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    written = []
    for frame, path in zip(wanted, drawn):
        target_file = hou.text.expandStringAtFrame(output, frame) \
            if len(wanted) == 1 or "$F" in output else viewport._numbered(output, f"{frame:g}")
        over_grey(path).save(target_file)
        written.append(target_file)

    report = {"filepath": written[0], "frames": wanted, "offscreen": True,
              "note": "An OpenGL ROP in a new hython drew the picture over a grey "
                      "background. The scene is not changed."}
    if len(written) > 1:
        report["images"] = [{"frame": frame, "filepath": path}
                            for frame, path in zip(wanted, written)]
    if aimed:
        report.update(aimed)
    return report
