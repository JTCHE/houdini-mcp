"""Make Houdini compute: cook a node over frames, write a cache, reset a solver."""
import hou

from . import as_list, unknown_mode
from ..handlers import cache, dops, timing
from ..handlers.geometry import failure

MUTATES = True

MODES = ("cook", "cache_write", "cache_clear", "sim_step", "sim_reset", "recook")


def run(paths, mode="cook", frame_range=None, frames=None, num_steps=1,
        parameters=None, force=True):
    if mode == "cook":
        # frame_range is [start, end] and means every frame between the two.
        # frames is a list, a number, or {"start": …, "end": …, "step": …}.
        wanted = frames
        if wanted is None and frame_range:
            wanted = {"start": frame_range[0], "end": frame_range[-1]}
        return _cook(as_list(paths), wanted, parameters, force)
    results = []
    for path in as_list(paths):
        try:
            results.append({"path": path, "result": _one(path, mode, frame_range, num_steps)})
        except Exception as error:
            node = hou.node(path)
            results.append({"path": path, "ok": False,
                            "error": f"{type(error).__name__}: {error}",
                            "nodes_with_errors": failure(node) if node else []})
    return results[0] if len(results) == 1 else {"count": len(results), "results": results}


def _cook(paths, frames, writes, force):
    """Write parameters, cook over the frames, and report the time of each one.

    One call covers a whole test: change a value, cook the range, read the
    seconds. The seconds are the number that decides a look, because the choice
    between a preview and a final setting is a choice about time for a frame.
    """
    nodes = []
    for path in paths:
        node = hou.node(path)
        if not node:
            raise ValueError(f"Node not found: {path}")
        nodes.append(node)

    report = {"paths": paths}
    if writes:
        # The same write path as parm_set, so a write that does nothing is
        # named here and not left to look like part of the result.
        report["parameters"] = [_write(path, values) for path, values in writes.items()]
    report.update(timing.cook_over(nodes, frames))
    return report


def _write(path, values):
    from ..handlers import parameters as handler
    return handler.set_parameters(path, values)


def _one(path, mode, frame_range, num_steps):
    if mode == "cache_write":
        return cache.write_cache(path, frame_range)
    if mode == "cache_clear":
        return cache.clear_cache(path)
    if mode == "sim_step":
        return dops.step_simulation(path, num_steps)
    if mode == "sim_reset":
        return dops.reset_simulation(path)
    if mode == "recook":
        return _recook(path)
    raise unknown_mode(mode, MODES)


def _recook(path):
    """Cook again each node at or under `path` that holds an error or a
    warning, the deepest first. A message that goes away was stale: an earlier
    cook left it, often a script that cooked frames while the viewport did."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")

    def told(item):
        return list(item.errors()) + list(item.warnings())

    # A ROP or a TOP node cooks by rendering or by making work items.
    held = [item for item in [node] + list(node.allSubChildren())
            if item.type().category().name() not in ("Driver", "Top") and told(item)]
    before = {item.path(): told(item) for item in held}
    for item in sorted(held, key=lambda item: -item.path().count("/")) + [node]:
        try:
            item.cook(force=True)
        except hou.OperationFailed:
            pass
    still = {item.path(): told(item) for item in held if told(item)}
    return {"path": path, "had_messages": before,
            "stale": [one for one in before if one not in still], "current": still,
            "note": "A stale message went away when its node cooked again. A current one "
                    "came back: it is real. Houdini keeps no frame or time for a message."}
