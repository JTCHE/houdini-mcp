"""A picture of the scene from a Houdini with no window.

hython has no viewport, and that is where most agent work happens. An OpenGL
ROP draws without one, so the same capture call answers in both kinds of
session: this builds a camera and a ROP, renders, and removes them again.
"""
import math
import os

import hou

from . import timing, viewport

ROP_NAME = "mcp_offscreen"
CAMERA_NAME = "mcp_offscreen_cam"

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
        geometry = node.geometry() if hasattr(node, "geometry") else None
        if geometry is not None:
            return geometry.boundingBox()
    box = hou.BoundingBox()
    for child in hou.node("/obj").children():
        try:
            if child.isObjectDisplayed() and hasattr(child, "geometry"):
                box.enlargeToContain(child.boundingBox())
        except (AttributeError, hou.OperationFailed):
            continue
    return box


def _orbit_direction(azimuth, elevation):
    """The direction from the target to the eye for an orbit angle in degrees.
    0 and 0 look along -Z, from the front, as in the viewport."""
    turn, lift = math.radians(azimuth or 0.0), math.radians(elevation or 0.0)
    return (math.sin(turn) * math.cos(lift), math.sin(lift),
            math.cos(turn) * math.cos(lift))


def _aim(camera, box, direction="persp", target=None, look_from=None,
         radius=None, fill=0.9):
    """Put the camera where it sees the box, with room around it. `direction`
    is a name, or a direction vector from the target to the eye."""
    middle = hou.Vector3(target) if target is not None else box.center()
    if look_from is not None:
        where = hou.Vector3(look_from)
    else:
        size = box.sizevec().length() or 1.0
        # The aperture and the focal length of the camera say how wide it sees.
        half = camera.evalParm("aperture") / (2.0 * camera.evalParm("focal"))
        away = radius if radius is not None else (size * 0.5) / (half * float(fill or 1.0))
        offset = hou.Vector3(direction if isinstance(direction, tuple)
                             else DIRECTIONS.get(direction, DIRECTIONS["persp"])).normalized()
        where = middle + offset * away
    camera.parmTuple("t").set(tuple(where))
    look = hou.hmath.buildRotateLookAt(where, middle, hou.Vector3(0, 1, 0))
    camera.parmTuple("r").set(tuple(look.extractRotates()))
    return {"look_from": list(where), "target": list(middle)}


def capture(node_path=None, output=None, frames=None, resolution=None,
            camera=None, direction="persp", target=None, look_from=None,
            radius=None, fill=0.9, shading=None, azimuth=None, elevation=None):
    """Draw a node, or the whole scene, at one frame or at several.

    The camera and the ROP live only for this call. Give `camera` to look
    through a camera of the scene instead.
    """
    node = None
    if node_path:
        node = hou.node(node_path)
        if not node:
            raise ValueError(f"Node not found: {node_path}")
        node.cook(force=False)

    wanted = timing.frame_list(frames, default=[hou.frame()])
    if not output:
        output = viewport.new_file("mcp_offscreen",
                                   ".$F4.jpg" if len(wanted) > 1 else ".jpg")
    output = os.path.abspath(output)
    folder = os.path.dirname(output)
    if folder:
        os.makedirs(folder, exist_ok=True)

    if camera:
        eye = hou.node(camera)
        if not eye:
            raise ValueError(f"Camera not found: {camera}")
        aimed = None
    else:
        eye = _kept_node("/obj", "cam", CAMERA_NAME)
        if azimuth is not None or elevation is not None:
            direction = _orbit_direction(azimuth, elevation)
        aimed = _aim(eye, _box(node), direction, target, look_from, radius, fill)

    rop = _kept_node("/out", "opengl", ROP_NAME)
    rop.parm("camera").set(eye.path())
    rop.parm("picture").set(output)
    rop.parm("tres").set(bool(resolution))
    if resolution:
        rop.parmTuple("res").set((int(resolution[0]), int(resolution[1])))
    # scenepath stays /obj: it names the network to render, and a geometry
    # object is not one. vobjects says which objects of it to draw.
    obj = _object_of(node) if node is not None else None
    rop.parm("vobjects").set(obj.name() if obj else "*")
    _shade(rop, shading)

    written = []
    # The ROP draws what the object displays, so the node to look at must hold
    # the display flag while it draws, and get it back after.
    with viewport.kept_display(node_path if node is not None else None):
        for frame in wanted:
            rop.render(frame_range=(frame, frame, 1), verbose=False)
            written.append(_written(output, frame))

    report = {"filepath": written[0], "frames": wanted, "offscreen": True,
              "note": f"This Houdini has no window, so an OpenGL ROP drew the "
                      f"picture. {rop.path()} and {eye.path()} stay in the "
                      f"scene and every capture reuses them."}
    if len(written) > 1:
        report["images"] = [{"frame": frame, "filepath": path}
                            for frame, path in zip(wanted, written)]
    if aimed:
        report.update(aimed)
    return report


def _kept_node(where, kind, name):
    """The node this tool works with, made once and reused after that.

    It is never destroyed, and that is not carelessness: hython hangs for good
    when an OpenGL ROP is destroyed after it has rendered. Two nodes with a
    plain name cost nothing, and the second capture is faster for it.
    """
    parent = hou.node(where)
    node = parent.node(name)
    if node and node.type().name() != kind:
        raise ValueError(f"{node.path()} is a {node.type().name()}, and this tool "
                         f"needs a {kind} there. Rename it or remove it.")
    return node or parent.createNode(kind, name)


def _object_of(node):
    """The object that holds a node. An OpenGL ROP chooses what to draw by
    object, so a SOP deep in a chain answers with the geometry above it."""
    while node is not None and node.parent() is not None:
        if node.parent().path() == "/obj":
            return node
        node = node.parent()
    return None


def _shade(rop, shading):
    """The shading of an OpenGL ROP, named the way the viewport names it."""
    modes = {"smooth": "smooth", "smooth_wire": "smoothwire", "flat": "flat",
             "wireframe": "wire"}
    parm = rop.parm("shademode")
    if not parm:
        return
    if shading is None:
        parm.set(modes["smooth"])
        return
    if shading not in modes:
        raise ValueError(f"Unknown shading: {shading}. Use: {list(modes)}")
    parm.set(modes[shading])


def _written(output, frame):
    """The file the ROP wrote for one frame, with $F replaced by the number."""
    return hou.text.expandStringAtFrame(output, frame)
