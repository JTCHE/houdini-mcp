"""A picture of a node network, drawn from the scene data: node boxes, flags,
names, comments, path text, dots, network boxes, sticky notes and wires in the
wire style of the network (straight or rounded).

It reads no screen pixels, so it needs no window, does not bring Houdini to
the front, and works in hython.
"""
import os

import hou
from PIL import Image, ImageDraw, ImageFont

from . import layout, viewport

MARGIN = 1.0        # network units around the drawn items
WIDTH = 1600        # target picture width in pixels
BACKGROUND = (46, 46, 46)
WIRE = (190, 190, 190)
TEXT = (230, 230, 230)
COMMENT = (150, 220, 150)
PATH_TEXT = (160, 160, 160)
FLAGS = {"display": (60, 140, 230), "render": (170, 90, 210),
         "template": (220, 120, 170), "bypass": (230, 200, 40)}


def _rgb(color, scale=1.0):
    return tuple(int(max(0.0, min(1.0, value * scale)) * 255) for value in color.rgb())


def _flag(node, read):
    try:
        return getattr(node, read)()
    except (hou.Error, AttributeError):
        return False


def capture(path=None, paths=None, output=None):
    """Draw the network at `path`, framed on the items in `paths` (default all)."""
    framed = [hou.item(one) for one in (paths or [])]
    if None in framed:
        raise ValueError(f"Not found: {[one for one, item in zip(paths, framed) if item is None]}")
    network = hou.node(path) if path else (framed[0].parent() if framed else hou.node("/obj"))
    if network is None:
        raise ValueError(f"Node not found: {path}")
    nodes = list(network.children())
    dots = list(network.networkDots())
    boxes = list(network.networkBoxes())
    notes = list(network.stickyNotes())
    shown = framed or nodes + dots + boxes + notes
    if not shown:
        raise ValueError(f"{network.path()} is empty: nothing to draw.")

    extents = [layout.box(item) if isinstance(item, hou.Node) else layout._shape(item)
               for item in shown]
    x0, y0 = min(e[0] for e in extents) - MARGIN, min(e[1] for e in extents) - MARGIN
    x1, y1 = max(e[2] for e in extents) + MARGIN, max(e[3] for e in extents) + MARGIN
    scale = max(12.0, min(70.0, WIDTH / (x1 - x0), 4000.0 / (y1 - y0)))
    width, height = int((x1 - x0) * scale), int((y1 - y0) * scale)
    picture = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(picture)
    font = ImageFont.load_default(size=max(8, int(layout.LINE * scale * 0.8)))

    def at(point):
        return ((point[0] - x0) * scale, (y1 - point[1]) * scale)

    def rect(item):
        left, bottom, right, top = layout._shape(item)
        return [at((left, top)), at((right, bottom))]

    for item in boxes:
        draw.rectangle(rect(item), fill=_rgb(item.color(), 0.35), outline=_rgb(item.color(), 0.6))
        draw.text(at((item.position()[0] + 0.1, item.position()[1] + item.size()[1] - 0.05)),
                  item.comment(), fill=TEXT, font=font)
    for item in notes:
        draw.rectangle(rect(item), fill=_rgb(item.color(), 0.8))
        draw.multiline_text(at((item.position()[0] + 0.1, item.position()[1] + item.size()[1]
                                - 0.1)), item.text(), fill=(20, 20, 20), font=font)

    curved = layout.rounded(network)
    for source, port, reader, index, via in layout._wires(nodes):
        points = [layout._out_point(source, port)] + \
            [layout._pos(dot) for dot in reversed(via)] + [layout._in_point(reader, index)]
        draw.line([at(point) for point in layout.wire_line(points, curved)], fill=WIRE,
                  width=max(1, int(scale / 30)), joint="curve")
    for dot in dots:
        x, y = at(layout._pos(dot))
        radius = max(2, scale * 0.07)
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=WIRE)

    for node in nodes:
        (left, top), (right, bottom) = rect(node)
        errors = bool(_flag(node, "errors"))
        draw.rectangle([left, top, right, bottom], fill=_rgb(node.color()),
                       outline=(230, 40, 40) if errors else (20, 20, 20),
                       width=3 if errors else 1)
        quarter = (right - left) / 4.0
        if _flag(node, "isBypassed"):
            draw.rectangle([left, top, left + quarter, bottom], fill=FLAGS["bypass"])
        if _flag(node, "isTemplateFlagSet"):
            draw.rectangle([right - 2 * quarter, top, right - quarter, bottom],
                           fill=FLAGS["template"])
        if _flag(node, "isDisplayFlagSet"):
            draw.rectangle([right - quarter, top, right, (top + bottom) / 2 if
                            _flag(node, "isRenderFlagSet") else bottom], fill=FLAGS["display"])
        if _flag(node, "isRenderFlagSet"):
            draw.rectangle([right - quarter, (top + bottom) / 2 if _flag(
                node, "isDisplayFlagSet") else top, right, bottom], fill=FLAGS["render"])
        draw.text((right + 0.1 * scale, top - layout.LINE * scale), node.type().description(),
                  fill=PATH_TEXT, font=font)
        # _text_lines gives the name, the shown comment lines, then the path text.
        comments = len(node.comment().splitlines()) if node.comment() and \
            node.isGenericFlagSet(hou.nodeFlag.DisplayComment) else 0
        for number, line in enumerate(layout._text_lines(node)):
            color = TEXT if number == 0 else COMMENT if number <= comments else PATH_TEXT
            draw.text((right + 0.1 * scale, top + number * layout.LINE * scale), line,
                      fill=color, font=font)

    output = os.path.abspath(output or viewport.new_file("mcp_network", ".png"))
    picture.save(output)
    return {"filepath": output, "network": network.path(), "items": len(shown),
            "wire_style": "rounded" if curved else "straight",
            "resolution": [width, height],
            "note": "Drawn from the scene data, not grabbed from the screen. Colors, flags "
                    "(blue display, purple render, pink template, yellow bypass), names, "
                    "comments, path text, dots and the wire style match the editor. Node "
                    "shapes and badges are not drawn. A red outline is a node with errors."}
