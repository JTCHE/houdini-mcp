"""The MCP tool surface. One module for each tool, found by its file name.

A tool module holds:
    tool(...)     the function that the client calls. Its name is the module
                  name, its docstring is what the client reads.
    ANNOTATIONS   optional ToolAnnotations, for example destructiveHint.
"""
import importlib
import pkgutil


def register(server) -> list:
    """Add every tool module in this package to the MCP server."""
    names = sorted(module.name for module in pkgutil.iter_modules(__path__))
    for name in names:
        module = importlib.import_module(f"{__name__}.{name}")
        server.add_tool(module.tool, name=name, annotations=getattr(module, "ANNOTATIONS", None))
    return names
