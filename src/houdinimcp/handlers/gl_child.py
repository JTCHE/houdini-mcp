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
        if job.get("color_by"):
            colour = holder.createNode("attribwrangle")
            colour.setInput(0, last)
            low, high = job.get("color_range") or (0.0, 1.0)
            # Blue at the low end, red at the high end. A vector reads as its
            # length.
            kind = KINDS[job["color_size"]]
            colour.parm("snippet").set(
                f'{kind} read = point(0, "{job["color_by"]}", @ptnum);\n'
                f'float value = {"abs" if kind == "float" else "length"}(read);\n'
                f'float t = clamp(fit(value, {float(low)}, {float(high)}, 0, 1), 0, 1);\n'
                f'@Cd = lerp({{0.1, 0.2, 1}}, {{1, 0.2, 0.1}}, t);')
            last = colour
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
            sys.exit(f"{node.type().name()}: {' '.join(node.errors())}")
    rop.render(frame_range=(1, job["count"], 1), verbose=False)


if __name__ == "__main__":
    with open(sys.argv[1]) as handle:
        main(json.load(handle))
