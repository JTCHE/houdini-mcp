"""The MCP tool surface. One module for each tool, found by its file name.

A tool module holds:
    tool(...)     the function that the client calls. Its name is the module
                  name, its docstring is what the client reads.
    ANNOTATIONS   optional ToolAnnotations, for example destructiveHint.
"""
import functools
import importlib
import inspect
import pkgutil
from typing import Optional

from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools import Tool

# name -> Tool, filled by build(). batch validates its steps against these.
TOOLS = {}


def build() -> list:
    """Every tool module in this package, as MCP tools."""
    for name in sorted(module.name for module in pkgutil.iter_modules(__path__)):
        module = importlib.import_module(f"{__name__}.{name}")
        tool = Tool.from_function(_guarded(module.tool), name=name,
                                  annotations=getattr(module, "ANNOTATIONS", None))
        # An argument that the tool does not take is refused, not dropped: a
        # dropped filter returns everything and reads as a filter that matched.
        model = tool.fn_metadata.arg_model
        model.model_config["extra"] = "forbid"
        model.model_rebuild(force=True)
        tool.parameters = model.model_json_schema(by_alias=True)
        TOOLS[name] = tool
    return list(TOOLS.values())


def validate(name: str, params: dict) -> None:
    """Refuse the arguments of one call the way the client call would."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"There is no tool '{name}'. Tools: {', '.join(TOOLS)}.")
    tool.fn_metadata.validate_arguments(params)


def _guarded(function):
    """The tool function, with two rules that every tool shares.

    An optional argument accepts null and then takes its default: a client
    sends null for an argument it leaves out, and a refusal that names an
    argument the caller never gave says nothing useful.

    Every failure keeps its text. The MCP SDK hides the text of any exception
    that is not a ToolError and sends only "Error executing tool <name>".
    """
    for parameter in inspect.signature(function).parameters.values():
        if parameter.default is not inspect.Parameter.empty and \
                parameter.annotation is not inspect.Parameter.empty:
            function.__annotations__[parameter.name] = Optional[parameter.annotation]

    @functools.wraps(function)
    def guarded(**arguments):
        given = {key: value for key, value in arguments.items() if value is not None}
        try:
            return function(**given)
        except ToolError:
            raise
        except Exception as error:
            raise ToolError(f"{type(error).__name__}: {error}") from error

    return guarded
