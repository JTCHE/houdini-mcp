"""Parameter read/write handlers.

Houdini accepts a write that changes nothing, and it says nothing. Five cases
do it: an expression, a keyframe, a lock, a parameter that another parameter
disables, and a channel reference, which sends the value to another node. One
function, `_write`, looks for all five, so every path that writes a parameter
reports the same truth.
"""
import difflib
import fnmatch

import hou


def _menu(template):
    """(tokens, labels) of a menu parameter, or (None, None)."""
    if not hasattr(template, "menuItems"):
        return None, None
    items = list(template.menuItems() or ())
    return (items, list(template.menuLabels() or ())) if items else (None, None)


def _expression(parm):
    try:
        return parm.expression()
    except hou.OperationFailed:
        return None


def _disable_rule(parm):
    """The rule that can grey this parameter out, as Houdini writes it.

    A disabled parameter keeps a value that the cook never reads, so a value
    that looks like live data is not. `hou.Parm.isDisabled` answers only in a
    graphical session, so the rule itself goes in the result as well: a caller
    can read the parameters that the rule names and decide.
    """
    try:
        conditionals = parm.parmTemplate().conditionals()
    except Exception:
        return None, None
    rule = conditionals.get(hou.parmCondType.DisableWhen)
    try:
        disabled = parm.isDisabled()
    except Exception:
        disabled = False
    return disabled, rule


def _disabled_by(parm):
    """A message when this parameter is disabled, or may be. Else None."""
    disabled, rule = _disable_rule(parm)
    if disabled:
        return rule or "another parameter or the node state"
    return None


def _referenced(parm):
    """The parameter that a channel reference points at, or None.

    `hou.Parm.set()` on a parameter that holds `ch("../other/parm")` does not
    change this parameter. It changes the one at the other end.
    """
    try:
        target = parm.getReferencedParm()
    except hou.OperationFailed:
        return None
    return target if target and target.path() != parm.path() else None


def describe(parm, with_menu=True):
    """Everything a caller must know about one parameter before it writes."""
    template = parm.parmTemplate()
    tokens, labels = _menu(template) if with_menu else (None, None)
    value = parm.eval()
    report = {
        "name": parm.name(),
        "label": template.label(),
        "type": template.type().name(),
        "value": value,
        "raw_value": parm.rawValue(),
        "is_at_default": parm.isAtDefault(),
    }
    if parm.isLocked():
        report["is_locked"] = True
    disabled, rule = _disable_rule(parm)
    if disabled:
        report["is_disabled"] = True
    # The rule matters where a value was written: a written value that the cook
    # ignores reads as live data. A default value under a rule is only noise.
    if rule and not report["is_at_default"]:
        report["disabled_when"] = rule
    expression = _expression(parm)
    if expression:
        report["expression"] = expression
        report["expression_language"] = str(parm.expressionLanguage())
    # An expression counts as one keyframe in Houdini. Only real keys matter
    # here, so an expression does not become a false "this is animated".
    if parm.keyframes() and not expression:
        report["keyframe_count"] = len(parm.keyframes())
    target = _referenced(parm)
    if target:
        report["reads_from"] = target.path()
    if tokens:
        report["menu_tokens"] = tokens
        report["menu_labels"] = labels
        # eval() on a menu that stores an index never returns the token, so a
        # caller that compares them is always wrong. Give both.
        if isinstance(value, int) and 0 <= value < len(tokens):
            report["menu_token"] = tokens[value]
    return report


def get_parameter(node_path, parm_name):
    """One parameter, with the reasons a write to it could do nothing."""
    node = _node(node_path)
    parm = node.parm(parm_name)
    if not parm:
        raise ValueError(_no_such(node, parm_name))
    return describe(parm)


def _node(node_path):
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    return node


def _no_such(node, parm_name):
    """The 'no such parameter' message, with the names that are close to it."""
    names = [parm.name() for parm in node.parms()]
    close = difflib.get_close_matches(parm_name, names, n=5, cutoff=0.5)
    hint = f" Close names on this node: {', '.join(close)}." if close else ""
    return f"Parameter not found: {parm_name} on {node.path()}.{hint}"


def _took(parm, value, tokens):
    """True when the parameter now holds what the caller asked for.

    A menu that stores an index gives the index back from eval(), never the
    token that was written, so the raw value decides for a token.
    """
    now = parm.eval()
    if now == value:
        return True
    if isinstance(value, str) and parm.rawValue() == value:
        return True
    if tokens and isinstance(value, str) and value in tokens:
        return now == tokens.index(value) or parm.rawValue() == value
    if isinstance(value, (int, float)) and isinstance(now, (int, float)):
        return abs(float(now) - float(value)) <= 1e-6 * max(1.0, abs(float(value)))
    return False


def _write(node, parm_name, value, follow_reference=False):
    """Write one parameter and report what really happened."""
    parm = node.parm(parm_name)
    if not parm:
        tuple_parm = node.parmTuple(parm_name)
        if tuple_parm and isinstance(value, (list, tuple)):
            return _write_tuple(tuple_parm, value, follow_reference)
        return {"parm": parm_name, "applied": False, "reason": _no_such(node, parm_name)}

    template = parm.parmTemplate()
    tokens, _labels = _menu(template)
    report = {"parm": parm_name, "old": parm.eval()}
    warnings = []

    target = _referenced(parm)
    if target and not follow_reference:
        return {**report, "applied": False, "reads_from": target.path(),
                "reason": f"this parameter reads {target.path()} through a channel "
                          f"reference, so a write would change that node, not this one. "
                          f"Call again with follow_reference=true to write "
                          f"{target.path()}, or write that parameter by its own path."}

    expression = _expression(parm)
    # Houdini counts an expression as one keyframe, so ask for keys only when
    # there is no expression. Otherwise every expression reads as animation.
    keyframes = parm.keyframes() if not expression else ()
    try:
        parm.set(value)
    except hou.PermissionError as error:
        return {**report, "applied": False, "reason": f"the parameter is locked: {error}"}
    except (hou.OperationFailed, TypeError) as error:
        return {**report, "applied": False,
                "reason": f"Houdini refused the value: {error}. The parameter type is "
                          f"{template.type().name()}."}

    report["new"] = parm.eval()
    report["raw"] = parm.rawValue()
    report["applied"] = _took(parm, value, tokens)
    if tokens:
        report["menu_tokens"] = tokens

    if target:
        report["wrote_to"] = target.path()
        warnings.append(f"the value went to {target.path()}, not to "
                        f"{node.path()}/{parm_name}, because this parameter reads it.")
    if expression and not report["applied"]:
        report["expression"] = expression
        report["reason"] = ("the parameter carries an expression, which still decides the "
                            "value. Remove it with mode 'revert', or write the expression.")
    elif keyframes:
        report["keyframe_count"] = len(parm.keyframes())
        warnings.append("the parameter is animated: the value became a new key at this frame.")
    elif not report["applied"]:
        report["reason"] = _refused_reason(parm, template, tokens, value)

    disabled, rule = _disable_rule(parm)
    if disabled:
        report["is_disabled"] = True
        warnings.append(f"the parameter is disabled by {rule or 'the node state'}, so the "
                        f"value is in the node and the cook does not read it. Change that "
                        f"condition first.")
    elif rule:
        report["disabled_when"] = rule
        warnings.append(f"this parameter is greyed out, and the cook ignores it, when "
                        f"{rule} is true. Houdini reports the state only in a graphical "
                        f"session, so read the parameters that this rule names and confirm "
                        f"that the value is live.")
    expanded = _expansion_warning(parm, template)
    if expanded:
        warnings.append(expanded)
    if warnings:
        report["warnings"] = warnings
    return report


def _refused_reason(parm, template, tokens, value):
    """Why a value did not take, named from the template instead of guessed."""
    if tokens:
        return (f"'{value}' is not a token of this menu. Tokens: {', '.join(map(str, tokens))}. "
                f"The parameter holds {parm.rawValue()!r} now.")
    if hasattr(template, "minValue") and isinstance(value, (int, float)):
        low, high = template.minValue(), template.maxValue()
        if template.minIsStrict() and value < low:
            return f"the value is below the strict minimum {low}."
        if template.maxIsStrict() and value > high:
            return f"the value is over the strict maximum {high}."
    return (f"Houdini kept {parm.eval()!r} for a write of {value!r}. The parameter type is "
            f"{template.type().name()}.")


def _expansion_warning(parm, template):
    """Houdini expands $VAR and `backticks` in the text of a string parameter.

    The text that VEX or a file name then gets is not the text that was
    written, and nothing reports it: a `$1` in a regular expression becomes an
    empty string, and the node cooks a wrong result with no error.
    """
    if template.type() != hou.parmTemplateType.String:
        return None
    try:
        written, used = parm.unexpandedString(), parm.eval()
    except hou.OperationFailed:
        return None
    if written == used:
        return None
    return (f"Houdini expanded variables in this text, so the value that the node uses is "
            f"not the value that was written. Written: {written!r}. Used: {used!r}. "
            f"Escape each dollar sign as \\$, or use another way to write it.")


def _write_tuple(parm_tuple, values, follow_reference):
    """A write to every component of a parameter tuple, for example t or scale."""
    node = parm_tuple.node()
    reports = [_write(node, parm.name(), value, follow_reference)
               for parm, value in zip(parm_tuple, values)]
    return {"parm": parm_tuple.name(), "components": reports,
            "applied": all(report.get("applied") for report in reports)}


def set_parameter(node_path, parm_name, value, follow_reference=False):
    """Set a single parameter value."""
    node = _node(node_path)
    report = _write(node, parm_name, value, follow_reference)
    if str(report.get("reason", "")).startswith("Parameter not found"):
        raise ValueError(report["reason"])
    return {"path": node_path, **report}


def set_parameters(node_path, parameters, follow_reference=False):
    """Set several parameters. Names that do not exist come back in the result."""
    node = _node(node_path)
    changes = [_write(node, name, value, follow_reference)
               for name, value in parameters.items()]
    return {
        "path": node_path,
        "changes": changes,
        "not_applied": [change["parm"] for change in changes if not change["applied"]],
    }


def press_button(node_path, parm_name, cook_after=True):
    """Press a button parameter, and report what the node says after it.

    A button starts work that fails later and in silence — a cache write, a
    reload, a resimulate — so the errors and the warnings of the node belong in
    the same answer as the press.
    """
    node = _node(node_path)
    parm = node.parm(parm_name)
    if not parm:
        raise ValueError(_no_such(node, parm_name))
    kind = parm.parmTemplate().type()
    if kind not in (hou.parmTemplateType.Button, hou.parmTemplateType.Toggle):
        raise ValueError(f"{node_path}/{parm_name} is a {kind.name()} parameter, not a button. "
                         f"Write a value to it with mode 'value'.")
    condition = _disabled_by(parm)
    parm.pressButton()
    report = {"path": node_path, "parm": parm_name, "pressed": True,
              "errors": list(node.errors()), "warnings": list(node.warnings())}
    if condition:
        report["is_disabled"] = True
        report["reason"] = (f"the button is disabled by {condition}. The press may have done "
                            f"nothing.")
    return report


def get_parameter_schema(node_path, parm=None, pattern=None):
    """The templates of the parameters: type, range, menu tokens.

    `parm` reads one. `pattern` keeps the names that match, for example
    "*field*". A large node has thousands of templates, and an answer that
    holds all of them is too big for a client to read.
    """
    node = _node(node_path)
    parms = _selected_parms(node, parm, pattern)
    schema = []
    for one in parms:
        template = one.parmTemplate()
        info = {
            "name": one.name(),
            "label": template.label(),
            "type": template.type().name(),
            "is_at_default": one.isAtDefault(),
        }
        tokens, labels = _menu(template)
        if tokens:
            info["menu_items"] = tokens
            info["menu_labels"] = labels
        if hasattr(template, "minValue"):
            info["min"] = template.minValue()
            info["max"] = template.maxValue()
        if one.isDisabled():
            info["is_disabled"] = True
        schema.append(info)
    return {"path": node_path, "count": len(schema), "parameters": schema}


def _selected_parms(node, parm=None, pattern=None):
    """The parameters that a caller asked for: one name, a pattern, or all."""
    if parm:
        one = node.parm(parm)
        if not one:
            raise ValueError(_no_such(node, parm))
        return [one]
    if pattern:
        return [one for one in node.parms()
                if fnmatch.fnmatch(one.name(), pattern)
                or pattern.lower() in one.name().lower()
                or pattern.lower() in one.parmTemplate().label().lower()]
    return list(node.parms())


def get_parameters(node_path, parm=None, pattern=None, has_expression=False,
                   changed_only=False):
    """Read the parameters of a node, with a filter.

    `changed_only` keeps a parameter that is not at its default, that carries an
    expression, or that has keys. An expression usually sits on a parameter that
    is at its default value, so a filter on the value alone hides the part that
    makes a scene time dependent.
    """
    node = _node(node_path)
    found = []
    for one in _selected_parms(node, parm, pattern):
        expression = _expression(one)
        keys = one.keyframes() if not _expression(one) else ()
        if has_expression and not expression:
            continue
        reasons = []
        if not one.isAtDefault():
            reasons.append("value")
        if expression:
            reasons.append("expression")
        if keys:
            reasons.append("keyframes")
        if changed_only and not reasons:
            continue
        report = describe(one)
        if reasons:
            report["in_list_because"] = reasons
        found.append(report)
    return {"path": node_path, "count": len(found),
            "parameter_count": len(node.parms()), "parameters": found}


def get_expression(node_path, parm_name):
    """Get the expression set on a parameter, if any."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parm = node.parm(parm_name)
    if not parm:
        raise ValueError(f"Parameter not found: {parm_name} on {node_path}")
    try:
        expr = parm.expression()
        lang = str(parm.expressionLanguage())
        return {"path": node_path, "parm": parm_name, "expression": expr, "language": lang}
    except hou.OperationFailed:
        return {"path": node_path, "parm": parm_name, "expression": None}


def revert_parameter(node_path, parm_name):
    """Revert a parameter to its default value."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parm = node.parm(parm_name)
    if not parm:
        raise ValueError(f"Parameter not found: {parm_name} on {node_path}")
    parm.revertToDefaults()
    return {"path": node_path, "parm": parm_name, "value": parm.eval(), "reverted": True}


def link_parameters(src_path, src_parm, dst_path, dst_parm):
    """Create a channel reference from dst_parm to src_parm."""
    src_node = hou.node(src_path)
    dst_node = hou.node(dst_path)
    if not src_node:
        raise ValueError(f"Source node not found: {src_path}")
    if not dst_node:
        raise ValueError(f"Destination node not found: {dst_path}")
    src_p = src_node.parm(src_parm)
    dst_p = dst_node.parm(dst_parm)
    if not src_p:
        raise ValueError(f"Source parameter not found: {src_parm}")
    if not dst_p:
        raise ValueError(f"Destination parameter not found: {dst_parm}")
    ref = f'ch("{src_p.path()}")'
    dst_p.setExpression(ref, hou.exprLanguage.Hscript)
    return {"src": src_p.path(), "dst": dst_p.path(), "expression": ref}


def lock_parameter(node_path, parm_name, locked=True):
    """Lock or unlock a parameter."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parm = node.parm(parm_name)
    if not parm:
        raise ValueError(f"Parameter not found: {parm_name} on {node_path}")
    parm.lock(locked)
    return {"path": node_path, "parm": parm_name, "locked": locked}


def create_spare_parameter(node_path, name, label, parm_type, default=None):
    """Add a spare parameter to a node."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    type_map = {
        "float": hou.FloatParmTemplate,
        "int": hou.IntParmTemplate,
        "string": hou.StringParmTemplate,
        "toggle": hou.ToggleParmTemplate,
    }
    template_cls = type_map.get(parm_type)
    if not template_cls:
        raise ValueError(f"Unknown parm type: {parm_type}. Use: {list(type_map.keys())}")
    if parm_type == "toggle":
        template = template_cls(name, label, default_value=bool(default) if default is not None else False)
    elif parm_type == "string":
        template = template_cls(name, label, 1, default_value=(str(default),) if default is not None else ("",))
    else:
        template = template_cls(name, label, 1, default_value=(default,) if default is not None else (0,))
    ptg = node.parmTemplateGroup()
    ptg.addParmTemplate(template)
    node.setParmTemplateGroup(ptg)
    return {"path": node_path, "parm": name, "type": parm_type, "created": True}


def create_spare_parameters(node_path, parameters):
    """Add multiple spare parameters to a node at once.

    parameters: list of dicts with keys: name, label, parm_type, default (optional)
    """
    results = []
    for p in parameters:
        result = create_spare_parameter(
            node_path, p["name"], p["label"], p["parm_type"], p.get("default")
        )
        results.append(result)
    return {"path": node_path, "created": results}
