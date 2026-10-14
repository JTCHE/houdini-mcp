"""A picture of the network editor, as the user sees it.

Every Houdini pane is a native GL drawable, so QWidget.grab() gives a black
image. What works is a grab of the screen pixels in the rectangle of the pane.
Screen pixels hold whatever window sits in front, so the grab runs only when
Houdini is the active window and is not minimised; in every other case it is
refused, with the reason.
"""
import os
import sys

import hou

from . import viewport

MARGIN = 1.5  # network units around the framed items


def _foreground():
    """None when the Houdini window is in front and shown, or the reason it is
    not."""
    window = hou.qt.mainWindow()
    if window.isMinimized():
        return "the Houdini window is minimised"
    if sys.platform == "win32":
        import ctypes
        user32 = ctypes.windll.user32
        process = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(process))
        if process.value != os.getpid():
            return "another application is in front of Houdini"
    elif not window.isActiveWindow():
        return "the Houdini window is not the active window"
    return None


def _bounds(items):
    """The rectangle of the items on the canvas, with a margin."""
    rect = hou.BoundingRect()
    for item in items:
        position, size = item.position(), item.size()
        rect.enlargeToContain(hou.BoundingRect(position[0], position[1],
                                               position[0] + size[0], position[1] + size[1]))
    rect.expand((MARGIN, MARGIN))
    return rect


def capture(path=None, paths=None, output=None):
    """Show the network at `path` (or of the nodes in `paths`), frame those
    nodes or all the items, grab the pane, and put the view back.

    A generator: the editor draws the new view only in the event loop, so the
    grab waits one step for it (see server._step).
    """
    reason = _foreground()
    if reason:
        raise RuntimeError(f"No network picture: {reason}. A grab reads screen pixels, so a "
                           f"window in front of Houdini would show in it. Ask the user to "
                           f"bring Houdini to the front, or read the graph with "
                           f"scene_overview mode 'network'.")
    editor = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
    if editor is None:
        raise RuntimeError("This Houdini window has no network editor pane.")
    framed = [hou.node(one) or hou.item(one) for one in (paths or [])]
    if None in framed:
        raise ValueError(f"Not found: {[one for one, item in zip(paths, framed) if item is None]}")
    network = hou.node(path) if path else (framed[0].parent() if framed else editor.pwd())
    if network is None:
        raise ValueError(f"Node not found: {path}")
    before_network, before_bounds = editor.pwd(), editor.visibleBounds()
    try:
        editor.setPwd(network)
        items = framed or list(network.allItems())
        if items:
            editor.setVisibleBounds(_bounds(items))
        # The editor draws the new view only when the event loop runs.
        yield 0.4, None
        output = os.path.abspath(output or viewport.new_file("mcp_network", ".png"))
        geometry = editor.qtScreenGeometry()
        screen = hou.qt.mainWindow().screen()
        origin = screen.geometry()
        picture = screen.grabWindow(0, geometry.x() - origin.x(), geometry.y() - origin.y(),
                                    geometry.width(), geometry.height())
        if picture.isNull() or not picture.save(output):
            raise RuntimeError(f"The grab of the network pane gave no image at {output}.")
    finally:
        try:
            editor.setPwd(before_network)
            editor.setVisibleBounds(before_bounds)
        except hou.Error:
            pass
    return {"filepath": output, "network": network.path(), "framed": len(items),
            "resolution": viewport.image_size(output),
            "note": "Screen pixels of the network pane, taken while Houdini was in front."}
