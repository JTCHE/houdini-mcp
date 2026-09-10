"""Make Houdini compute: cook a node, write or clear a cache, step a simulation."""
import hou

from . import as_list, unknown_mode
from ..handlers import cache, dops

MUTATES = True

MODES = ("cook", "cache_write", "cache_clear", "sim_step", "sim_reset")


def run(paths, mode="cook", frame_range=None, num_steps=1):
    results = []
    for path in as_list(paths):
        try:
            results.append({"path": path, "result": _one(path, mode, frame_range, num_steps)})
        except Exception as error:
            results.append({"path": path, "error": f"{type(error).__name__}: {error}"})
    return results[0] if len(results) == 1 else {"count": len(results), "results": results}


def _one(path, mode, frame_range, num_steps):
    if mode == "cook":
        node = hou.node(path)
        if not node:
            raise ValueError(f"Node not found: {path}")
        node.cook(force=True)
        # A cook error gives an empty result and no exception. Report it here.
        return {"cooked": True, "errors": list(node.errors()), "warnings": list(node.warnings())}
    if mode == "cache_write":
        return cache.write_cache(path, frame_range)
    if mode == "cache_clear":
        return cache.clear_cache(path)
    if mode == "sim_step":
        return dops.step_simulation(path, num_steps)
    if mode == "sim_reset":
        return dops.reset_simulation(path)
    raise unknown_mode(mode, MODES)
