"""One module for each MCP tool, mirroring src/bridge/tools/.

A tool module holds:
    MUTATES        True when the tool can change the scene. The dispatch puts a
                   mutating call in one undo group, so no hand-kept list of
                   command names can drift from the code. A function of the
                   params when only some modes change the scene.
    run(**params)  the work. Plain JSON in, plain JSON out.
"""
import importlib
import pkgutil

import hou

from ..handlers import changes

MODULES = sorted(module.name for module in pkgutil.iter_modules(__path__))


def module_of(command: str):
    if command not in MODULES:
        raise ValueError(f"Unknown tool '{command}'. This plugin has: {', '.join(MODULES)}. "
                         f"The bridge and the plugin are different versions: run the "
                         f"installer again and restart Houdini.")
    return importlib.import_module(f"{__name__}.{command}")


def dispatch(command: str, params: dict, label: str = None):
    """Run one tool. Wraps a mutating tool in one undo group, named `label`."""
    module = module_of(command)
    mutates = getattr(module, "MUTATES", False)
    if mutates(params) if callable(mutates) else mutates:
        try:
            with hou.undos.group(label or f"MCP: {command}"):
                return module.run(**params)
        finally:
            # What this call changed is not a change of the user.
            changes.refresh()
    return module.run(**params)


def as_list(value):
    """One item or a list of items, always as a list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


class Arguments(dict):
    """The arguments of one item. A missing one names itself and the mode,
    because a bare KeyError says nothing about what the call lacks."""

    def __init__(self, mode, values):
        super().__init__(values)
        self.mode = mode
        self.read = {"mode"}

    def __missing__(self, key):
        raise ValueError(f"mode '{self.mode}' needs the argument '{key}'.")

    def __getitem__(self, key):
        self.read.add(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self.read.add(key)
        return super().get(key, default)

    def __contains__(self, key):
        self.read.add(key)
        return super().__contains__(key)

    def unread(self):
        """The arguments that the mode did not look at. A call that gives one
        expects an effect that did not happen."""
        return sorted(key for key in self.keys() if key not in self.read)


def items_of(mode, items, defaults):
    """One item or a list of them, each merged over the defaults. An item can
    carry its own `mode`; the mode of the call is the default."""
    return ([Arguments(item.get("mode", mode), {**defaults, **item}) for item in as_list(items)]
            or [Arguments(mode, defaults)])


def run_items(mode, items, defaults, one):
    """Run one(mode, arguments) for each item. A failed item keeps its error,
    and an argument that the mode did not read is reported, not ignored."""
    results = []
    for arguments in items_of(mode, items, defaults):
        try:
            result = one(arguments.mode, arguments)
        except Exception as error:
            result = {"error": f"{type(error).__name__}: {error}", "item": dict(arguments)}
        unread = arguments.unread()
        if unread and isinstance(result, dict) and "error" not in result:
            result["ignored_arguments"] = (
                f"mode '{arguments.mode}' does not read {', '.join(unread)}; "
                f"they had no effect.")
        results.append(result)
    return results[0] if len(results) == 1 else {"count": len(results), "results": results}


def unknown_mode(mode, known):
    return ValueError(f"Unknown mode '{mode}'. Use one of: {', '.join(known)}.")
