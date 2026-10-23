"""VEX wrangle creation and validation handlers."""
import os
import re

import hou

from . import nodes as node_handler
from . import parameters


def create_wrangle(parent_path, wrangle_type="attribwrangle", name=None, code="",
                   code_file=None, input_path=None):
    """Create a VEX wrangle node with its code, and report what it says."""
    parent = hou.node(parent_path)
    if not parent:
        raise ValueError(f"Parent not found: {parent_path}")
    node = parent.createNode(wrangle_type, node_name=name)
    if input_path:
        source = hou.node(input_path)
        if not source:
            raise ValueError(f"Input node not found: {input_path}")
        node.setInput(0, source)
    placed = node_handler.place_node(node)
    report = {"path": node.path(), "name": node.name(), "type": wrangle_type,
              "position": list(node.position()), **placed}
    if code or code_file:
        report.update(write_snippet(node.path(), code, code_file))
    return report


def size_note(code):
    """The house rule for VEX that a person reads: built-in nodes first, and a
    wrangle only when it is about ten lines or less. None when the code keeps
    to it."""
    short = sorted(set(re.findall(r"\b(?:float|int|vector|vector2|vector4|string|matrix|"
                                  r"matrix3|dict)\s+([a-z])\b", code)) |
                   {f"@{name}" for name in re.findall(r"\b[fiuvps]@([a-z]\d?)\b", code)})
    if short:
        return (f"Name each variable and attribute in plain words, in camelCase "
                f"(outwardSpeed, distanceToShell): {', '.join(short)} says nothing to the "
                f"person who opens this wrangle.")
    lines = [line for line in code.splitlines()
             if line.strip() and not line.strip().startswith("//")]
    builds = ("addpoint" in code or "addprim" in code) and re.search(
        r"\b(for|foreach|while)\b", code)
    if len(lines) <= 10 and not builds:
        return None
    return (f"This snippet has {len(lines)} lines"
            f"{' and makes geometry in a loop' if builds else ''}. Look for the chain of "
            f"built-in nodes first (Sweep, Carve, Scatter, Copy to Points, Attribute Noise, "
            f"Attribute Randomize, Attribute Remap, Blast...): the user reads a network more "
            f"easily than code. Keep VEX for what is simpler in about ten lines.")


def _snippet_parm(node, parm="snippet"):
    found = node.parm(parm)
    if found:
        return found
    # A wrangle node type names its code parameter in more than one way.
    for name in ("snippet", "vexpression", "code", "soppath"):
        found = node.parm(name)
        if found:
            return found
    raise ValueError(f"Node {node.path()} has no code parameter. The names that were "
                     f"tried: snippet, vexpression, code.")


def write_snippet(node_path, code=None, code_file=None, replace=None, parm="snippet"):
    """Write VEX into a node, and cook it so that a compile error comes back now.

    Three ways to give the code, because a long snippet that goes through the
    conversation for each small change costs more than the change:
        code       — the whole text.
        code_file  — a file that Houdini reads. The text never travels twice.
        replace    — a list of {old, new}. Each `old` must match one time in the
                     code that the node holds now, so a wrong edit fails here
                     and not in the cook.
    """
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    target = _snippet_parm(node, parm)
    before = target.unexpandedString()

    if code_file:
        if not os.path.isfile(code_file):
            raise ValueError(f"There is no file at {code_file}. Houdini reads this path, so "
                             f"it must be a path on the machine that runs Houdini.")
        with open(code_file, encoding="utf-8") as handle:
            code = handle.read()
    if replace:
        code = before if code is None else code
        for edit in replace:
            old, new = edit["old"], edit["new"]
            found = code.count(old)
            if found != 1:
                raise ValueError(f"The text to replace matches {found} times, and it must "
                                 f"match one time: {old!r}. Read the code with node_inspect "
                                 f"mode 'code' and give more of the lines around it.")
            code = code.replace(old, new)
    if code is None:
        raise ValueError("Give code, code_file or replace.")

    target.set(code)
    report = {"path": node_path, "parm": target.name(), "characters": len(code),
              "source": code_file or ("replace" if replace else "code")}
    # Houdini expands $ and backticks in the snippet text before VEX compiles
    # it, and it reports nothing. A `$1` in a regular expression becomes an
    # empty string and the node cooks a wrong result.
    expanded = parameters._expansion_warning(target, target.parmTemplate())
    if expanded:
        report["warning"] = expanded
    rule = size_note(code)
    if rule:
        report["house_rule"] = rule
    try:
        node.cook(force=True)
    except hou.OperationFailed:
        pass  # the message is in node.errors(), which the caller must read
    report["errors"] = list(node.errors())
    report["warnings"] = list(node.warnings())
    return report


def get_wrangle_code(node_path, parm="snippet"):
    """Get the VEX code from a wrangle node, as it was written and as it is used."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    target = _snippet_parm(node, parm)
    written, used = target.unexpandedString(), target.eval()
    report = {"path": node_path, "parm": target.name(), "code": written}
    if written != used:
        report["code_after_expansion"] = used
        report["warning"] = ("Houdini expanded variables in this text. VEX compiles the "
                             "expanded text, not the text that is written here.")
    return report


def create_vex_expression(parent_path, attrib_name, expression, run_over="Points"):
    """Create a wrangle node that evaluates a VEX expression and stores it in an attribute."""
    parent = hou.node(parent_path)
    if not parent:
        raise ValueError(f"Parent not found: {parent_path}")
    code = f'@{attrib_name} = {expression};'
    node = parent.createNode("attribwrangle", node_name=f"expr_{attrib_name}")
    node.parm("snippet").set(code)
    class_parm = node.parm("class")
    if class_parm:
        run_over_map = {"Detail": 0, "Points": 1, "Vertices": 2, "Primitives": 3}
        val = run_over_map.get(run_over, 1)
        class_parm.set(val)
    return {"path": node.path(), "attrib": attrib_name, "code": code}


def validate_vex(code):
    """Validate VEX by compiling it in a throwaway wrangle and reading cook errors.

    HOM has no direct VEX-string syntax checker, so we cook a temporary
    attribwrangle (fed one point) and report any compile/cook errors.
    """
    tmp = hou.node("/obj").createNode("geo", node_name="__vex_validate_tmp")
    try:
        add = tmp.createNode("add")
        add.parm("points").set(1)
        wr = tmp.createNode("attribwrangle")
        wr.parm("snippet").set(code)
        wr.setInput(0, add)
        try:
            wr.cook(force=True)
        except hou.OperationFailed:
            pass  # cook errors are captured via wr.errors() below
        errors = list(wr.errors())
        return {"valid": len(errors) == 0, "errors": errors or None}
    finally:
        tmp.destroy()
