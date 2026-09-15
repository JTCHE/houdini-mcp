"""File caches: which nodes write one, and what is on disk for it.

A cache node is where a look iteration stops being cheap. The question an agent
has is always the same: is this cached, for which frames, and is the node
reading the files or cooking them again.
"""
import glob
import os
import re
import time

import hou

# The parameter that names the file a node writes. The first one a node has
# says which kind of cache node it is.
OUTPUT_PARMS = ("sopoutput", "file", "filename", "picture", "dopoutput",
                "lopoutput", "copoutput")
WRITE_BUTTONS = ("execute", "render", "save")


def _files_on_disk(pattern):
    """What the cache wrote: how many frames, how large, and how old.

    $F4 becomes a wildcard, so one look at the folder answers for the whole
    sequence instead of one question for each frame.
    """
    if not pattern:
        return None
    # $F, $F4, $SF and the like all stand for the frame number.
    wild = re.sub(r"\$[A-Z]+\d*", "*", pattern)
    try:
        found = [path for path in glob.glob(wild) if os.path.isfile(path)]
    except OSError:
        return None
    if not found:
        return {"frames_written": 0, "note": "Nothing is written for this pattern yet."}
    newest = max(os.path.getmtime(path) for path in found)
    return {
        "frames_written": len(found),
        "bytes": sum(os.path.getsize(path) for path in found),
        "newest": time.strftime("%Y-%m-%d %H:%M", time.localtime(newest)),
        "folder": os.path.dirname(found[0]),
    }


def _output_parm(node):
    """The parameter that names what a node writes, and its name."""
    for name in OUTPUT_PARMS:
        parm = node.parm(name)
        if parm:
            return parm
    return None


def _is_cache(node):
    """A node that writes a file and can be told to write it now.

    That is the whole test, and it holds for a File Cache SOP, a ROP Geometry
    node, an Alembic ROP and anything an asset builder writes tomorrow.
    """
    if node.isInsideLockedHDA():
        return False
    if not _output_parm(node):
        return False
    return any(node.parm(name) for name in WRITE_BUTTONS)


def describe_cache(node):
    """One row: what the node writes, for which frames, and what is on disk."""
    parm = _output_parm(node)
    row = {"path": node.path(), "type": node.type().name(),
           "output_parm": parm.name()}
    try:
        row["output"] = parm.eval()
    except hou.OperationFailed as error:
        row["output"] = None
        row["output_error"] = str(error)
    row["unexpanded"] = _raw(parm)

    for name, label in (("version", "version"), ("loadfromdisk", "load_from_disk"),
                        ("filemethod", "file_method"), ("basename", "basename"),
                        ("timedependent", "time_dependent")):
        found = node.parm(name)
        if found:
            row[label] = found.eval()
    start, end, step = node.parm("f1"), node.parm("f2"), node.parm("f3")
    if start and end:
        row["frame_range"] = [start.eval(), end.eval()] + ([step.eval()] if step else [])
    row["on_disk"] = _files_on_disk(row.get("output"))
    return row


def _raw(parm):
    """The text of a parameter before Houdini expands it.

    A parameter that carries an expression or a keyframe has no unexpanded
    string at all, and asking for one raises. The expression is the answer
    there, and it says more than the path of one frame.
    """
    try:
        return parm.unexpandedString()
    except (AttributeError, hou.OperationFailed):
        pass
    try:
        return parm.expression()
    except hou.OperationFailed:
        return None


def list_caches(root_path="/obj"):
    """Every node under a root that writes a cache, with its state on disk.

    Nodes inside a locked asset are left out: they are the machinery of an
    asset, not a cache the user writes.
    """
    root = hou.node(root_path)
    if not root:
        raise ValueError(f"Root not found: {root_path}")
    rows = []
    for node in root.allSubChildren():
        try:
            if not _is_cache(node):
                continue
        except hou.Error:
            continue
        try:
            rows.append(describe_cache(node))
        except Exception as error:
            # Say which node could not be read. A row that quietly disappears
            # reads as "there is no cache here", which is the wrong answer.
            rows.append({"path": node.path(), "type": node.type().name(),
                         "error": f"{type(error).__name__}: {error}"})
    written = sum(1 for row in rows if (row.get("on_disk") or {}).get("frames_written"))
    return {"root": root_path, "count": len(rows), "written": written, "caches": rows}


def get_cache_status(path):
    """Get cache status for a file cache node."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    status = {"path": path, "type": node.type().name()}
    for parm_name in ["cachedir", "sopoutput", "file", "loadfromdisk", "basename"]:
        parm = node.parm(parm_name)
        if parm:
            status[parm_name] = str(parm.eval())
    return status


def clear_cache(path):
    """Clear cache on a file cache node by pressing the clear button."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    # Try common clear/delete cache button names
    for btn_name in ["clearcache", "clear", "execute"]:
        parm = node.parm(btn_name)
        if parm:
            parm.pressButton()
            return {"path": path, "cleared": True, "button": btn_name}
    raise ValueError(f"No clear cache button found on {path}")


def write_cache(path, frame_range=None):
    """Write cache for a file cache node."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    # Try common write/save buttons
    for btn_name in ["execute", "save", "render"]:
        parm = node.parm(btn_name)
        if parm:
            if frame_range and len(frame_range) == 2:
                f1 = node.parm("f1")
                f2 = node.parm("f2")
                if f1:
                    f1.set(frame_range[0])
                if f2:
                    f2.set(frame_range[1])
            parm.pressButton()
            return {"path": path, "writing": True, "button": btn_name}
    raise ValueError(f"No write cache button found on {path}")
