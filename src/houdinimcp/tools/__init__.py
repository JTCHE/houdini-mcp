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
        with hou.undos.group(label or f"MCP: {command}"):
            return module.run(**params)
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

    def __missing__(self, key):
        raise ValueError(f"mode '{self.mode}' needs the argument '{key}'.")


def items_of(mode, items, defaults):
    """One item or a list of them, each merged over the defaults."""
    return ([Arguments(mode, {**defaults, **item}) for item in as_list(items)]
            or [Arguments(mode, defaults)])


def unknown_mode(mode, known):
    return ValueError(f"Unknown mode '{mode}'. Use one of: {', '.join(known)}.")
