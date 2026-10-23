"""The MCP tool surface. One module for each tool, found by its file name.

A tool module holds:
    tool(...)     the function that the client calls. Its name is the module
                  name, its docstring is what the client reads.
    ANNOTATIONS   ToolAnnotations: what the tool can change.
    PARAMS        the description of each argument, by name. The client reads
                  it in the input schema, next to the type.
"""
import difflib
import functools
import importlib
import inspect
import pkgutil
import re
from typing import Optional

from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.tools import Tool
from mcp.server.mcpserver.utilities.func_metadata import FuncMetadata
from pydantic import ValidationError
from pydantic_core import PydanticCustomError

# name -> Tool, filled by build(). batch validates its steps against these.
TOOLS = {}
# name -> (the argument that names the mode, the modes), for the same check.
MODES = {}


def build() -> list:
    """Every tool module in this package, as MCP tools."""
    for name in sorted(module.name for module in pkgutil.iter_modules(__path__)):
        module = importlib.import_module(f"{__name__}.{name}")
        tool = Tool.from_function(_guarded(module.tool), name=name,
                                  annotations=module.ANNOTATIONS)
        tool.description = _with_modes(name, tool.description, module)
        # An argument that the tool does not take is refused, not dropped: a
        # dropped filter returns everything and reads as a filter that matched.
        model = tool.fn_metadata.arg_model
        model.model_config["extra"] = "forbid"
        model.model_rebuild(force=True)
        tool.parameters = model.model_json_schema(by_alias=True)
        properties = tool.parameters["properties"]
        if set(module.PARAMS) != set(properties):
            raise RuntimeError(f"{name}.PARAMS must describe exactly: {', '.join(properties)}.")
        # The title that pydantic makes from a name says nothing the name does not.
        tool.parameters.pop("title", None)
        for key, text in module.PARAMS.items():
            schema = properties[key]
            schema.pop("title", None)
            # Every optional argument takes null (see _guarded), so the schema
            # need not say so for each one.
            kinds = [kind for kind in schema.get("anyOf", ()) if kind != {"type": "null"}]
            if "anyOf" in schema:
                del schema["anyOf"]
                schema.update(kinds[0] if len(kinds) == 1 else {"anyOf": kinds})
            if "default" in schema and schema["default"] is None:
                del schema["default"]
            schema["description"] = text
        tool.fn_metadata = _Metadata.model_construct(**{
            key: getattr(tool.fn_metadata, key) for key in FuncMetadata.model_fields})
        TOOLS[name] = tool
    return list(TOOLS.values())


def _with_modes(name, description, module):
    """The description with the names of all modes after its first paragraph.

    A client can cut a long description, and the modes come last in it, so an
    agent did not know that a mode exists and wrote a script for it.
    """
    key = "mode" if "mode" in module.PARAMS else "action"
    modes = re.findall(r'"(\w+)"', module.PARAMS.get(key, ""))
    if not modes:
        return description
    MODES[name] = (key, modes)
    documented = re.findall(r'^\s+"(\w+)"\s*—', description, re.M)
    if set(modes) != set(documented):
        raise RuntimeError(f"{name}: PARAMS['{key}'] names {modes}, the docstring documents "
                           f"{documented}.")
    first, _, rest = description.partition("\n\n")
    indent = rest[:len(rest) - len(rest.lstrip(" "))]
    return f"{first}\n\n{indent}{key.title()}s: {', '.join(modes)}.\n\n{rest}"


class _Metadata(FuncMetadata):
    """The SDK reads a text argument as JSON when the type of the argument is
    not plain `str`, so that a list sent as text becomes a list. An optional
    argument is not plain `str`, and then the text "null" becomes nothing and
    "true" a boolean: node_type "null" was lost. Text that reads as null or as
    a boolean stays text; a list or an object is still read."""

    def validate_arguments(self, arguments):
        """An argument that the tool does not take names the argument it is
        close to: `path` where the tool takes `paths`."""
        try:
            return super().validate_arguments(arguments)
        except ValidationError as error:
            names = list(self.arg_model.model_fields)
            details = []
            for found in error.errors():
                if found["type"] == "extra_forbidden":
                    near = difflib.get_close_matches(str(found["loc"][0]), names, 1, 0.6)
                    hint = f"Did you mean '{near[0]}'? " if near else ""
                    found = {**found, "type": PydanticCustomError(
                        "unknown_argument",
                        f"This tool has no such argument. {hint}It takes: {', '.join(names)}.")}
                found.pop("msg", None)
                found.pop("url", None)
                details.append(found)
            raise ValidationError.from_exception_data(error.title, details) from error

    def pre_parse_json(self, data):
        parsed = super().pre_parse_json(data)
        return {key: data[key] if isinstance(data[key], str)
                and (value is None or isinstance(value, bool)) else value
                for key, value in parsed.items()}


def validate(name: str, params: dict) -> None:
    """Refuse the arguments of one call the way the client call would."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"There is no tool '{name}'. Tools: {', '.join(TOOLS)}.")
    tool.fn_metadata.validate_arguments(params)
    # A mode is text to the schema, so a wrong one passes it and fails only
    # when the step runs: then the whole batch rolls back.
    key, modes = MODES.get(name, (None, ()))
    items = params.get("items")
    for item in [params] + (items if isinstance(items, list) else [items] if items else []):
        mode = item.get(key) if isinstance(item, dict) else None
        if mode is not None and mode not in modes:
            near = difflib.get_close_matches(str(mode), modes, 1, 0.5)
            raise ToolError(f"{name} has no {key} '{mode}'. "
                            f"{f'Did you mean {near[0]!r}? ' if near else ''}"
                            f"Its {key}s: {', '.join(modes)}.")


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
