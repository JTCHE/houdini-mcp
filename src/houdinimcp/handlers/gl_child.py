"""Draw frames with an OpenGL ROP. Runs in a new hython, never in the session.

hython 22.0 stops with a segmentation fault on the second OpenGL ROP render
in one process, with no MCP code involved. One render call over a range is
safe. So the session writes the geometry of each frame to disk, and this
script draws all the frames in one render and exits.

Usage: hython gl_child.py job.json
"""
import json
import sys

import hou

KINDS = {1: "float", 2: "vector2", 3: "vector", 4: "vector4"}
MOTION = ("tx", "ty", "tz", "rx", "ry", "rz", "focal", "aperture", "orthowidth")


def main(job):
    drawn = []
    for index, pattern in enumerate(job["sources"]):
        holder = hou.node("/obj").createNode("geo", f"source{index}")
        last = holder.createNode("file")
        last.parm("file").set(pattern)
        if job.get("slab"):
            # A thin cut through the middle: the inside of a solid cloud shows.
            # A Blast keeps every point when it cannot read its group, so a
            # wrangle removes them.
            axis, thickness = "xyz".index(job["slab"][0]), float(job["slab"][1])
            last = _wrangle(holder, last, "slab",
                            f'if (abs(@P[{axis}] - getbbox_center(0)[{axis}]) > '
                            f'{thickness / 2}) removepoint(0, @ptnum);')
        if job.get("color_by"):
            low, high = job.get("color_range") or (0.0, 1.0)
            kind = KINDS[job["color_size"]]
            # Blue at the low end, red at the high end. A vector reads as its
            # length. A contour step colours by the fraction of the value over
            # the step, so the lines of equal value show the shape of a field.
            shade = (f'frac(value / {float(job["contour"])})' if job.get("contour") else
                     f'clamp(fit(value, {float(low)}, {float(high)}, 0, 1), 0, 1)')
            last = _wrangle(holder, last, "colour",
                            f'{kind} read = point(0, "{job["color_by"]}", @ptnum);\n'
                            f'float value = {"abs" if kind == "float" else "length"}(read);\n'
                            f'float t = {shade};\n'
                            f'@Cd = lerp({{0.1, 0.2, 1}}, {{1, 0.2, 0.1}}, t);')
        if job.get("vectors"):
            # One line along the vector from a share of the points, at most
            # about 3000 lines, so that the picture stays readable.
            last = _wrangle(holder, last, "vectors",
                            f'int stride = max(1, npoints(0) / 3000);\n'
                            f'if (@ptnum % stride == 0) {{\n'
                            f'    vector tip = @P + vector(point(0, "{job["color_by"]}", '
                            f'@ptnum)) * {float(job["vectors"])};\n'
                            f'    int end = addpoint(0, tip);\n'
                            f'    setpointattrib(0, "Cd", end, @Cd);\n'
                            f'    addprim(0, "polyline", @ptnum, end);\n'
                            f'}}')
        last.setDisplayFlag(True)
        last.setRenderFlag(True)
        drawn.append(last)

    eye = hou.node("/obj").createNode("cam", "eye")
    eye.parmTuple("res").set(tuple(job["size"]))
    views = job["views"]
    eye.parm("projection").set(views[0]["projection"])
    for name in MOTION:
        values = [view[name] for view in views]
        if len(set(values)) == 1:
            eye.parm(name).set(values[0])
            continue
        # One key on every frame: the ROP draws whole frames only, so the
        # curve between keys is never read.
        for frame, value in enumerate(values, 1):
            eye.parm(name).setKeyframe(hou.Keyframe(value, hou.frameToTime(frame)))

    rop = hou.node("/out").createNode("opengl")
    rop.parm("camera").set(eye.path())
    rop.parm("picture").set(job["picture"])
    rop.parm("tres").set(True)
    rop.parmTuple("res").set(tuple(job["size"]))
    rop.parm("shadingmode").set(job["shading"])
    hou.setFrame(1)
    for node in drawn:
        node.cook(force=True)
        if node.errors():
            sys.exit(f"{node.name()}: {' '.join(node.errors())}")
        cut = node.parent().node("slab")
        if cut is not None and not cut.geometry().points():
            sys.exit(f"The slab of {job['slab'][1]} along {job['slab'][0]} kept no point. "
                     f"Make it thicker than the space between the points.")
        if job.get("vectors"):
            before = len(node.inputs()[0].geometry().prims())
            if len(node.geometry().prims()) == before:
                sys.exit("The vector lines came out empty.")
    rop.render(frame_range=(1, job["count"], 1), verbose=False)


def _wrangle(holder, above, name, code):
    node = holder.createNode("attribwrangle", name)
    node.setInput(0, above)
    node.parm("snippet").set(code)
    return node


if __name__ == "__main__":
    with open(sys.argv[1]) as handle:
        main(json.load(handle))
