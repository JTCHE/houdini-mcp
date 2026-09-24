"""Parameter read/write handlers.

Houdini accepts a write that changes nothing, and it says nothing. These cases
do it: an expression, a keyframe, a lock, a parameter that another parameter
disables or hides, a strict range that clamps the value, a bit field written
by its token, and a channel reference, which sends the value to another node.
One function, `_write`, looks for all of them, so every path that writes a
parameter reports the same truth. `execute` reports the same through
`script_write_note`.
"""
import difflib
import fnmatch
import operator
import re

import hou


def _menu(template):
    """(tokens, labels) of a menu parameter, or (None, None)."""
    if not hasattr(template, "menuItems"):
        return None, None
    items = list(template.menuItems() or ())
    return (items, list(template.menuLabels() or ())) if items else (None, None)


def _bits(template):
    """{token: bit} of a menu whose value is a sum of bits, or None.

    Such a menu takes several items at once, and a write of one token stores
    the index of the item, not its bit: "rotate" becomes 1, which means
    "translate".
    """
    if template.type() != hou.parmTemplateType.Menu or             template.menuType() != hou.menuType.StringToggle:
        return None
    return {token: 1 << index for index, token in enumerate(template.menuItems())}


def _expression(parm):
    try:
        return parm.expression()
    except hou.OperationFailed:
        return None


# One term of a Disable When or Hide When rule: `name op value`.
_TERM = re.compile(r"""(\w+(?:\(\d+\))?)\s*(==|!=|<=|>=|=~|!~|<|>)\s*("[^"]*"|'[^']*'|[^\s"']+)""")
_COMPARE = {"==": operator.eq, "!=": operator.ne, "<": operator.lt, ">": operator.gt,
            "<=": operator.le, ">=": operator.ge}


def _term_holds(node, name, op, value):
    """True or False for one term, None for a form this reader does not know."""
    value = value.strip("\"'")
    function = re.fullmatch(r"hasinput\((\d+)\)", name)
    if function:
        index = int(function.group(1))
        inputs = node.inputs()
        text = number = int(index < len(inputs) and inputs[index] is not None)
    else:
        other = node.parm(name)
        if other is None:
            return None
        try:
            text, number = other.evalAsString(), other.eval()
        except hou.OperationFailed:
            return None
    if op in ("=~", "!~"):
        return fnmatch.fnmatch(str(text), value) == (op == "=~")
    try:
        return _COMPARE[op](float(number), float(value))
    except (TypeError, ValueError):
        # A menu compares its token, and a string its text.
        return _COMPARE[op](str(text), value)


def _rule_holds(node, rule):
    """Whether a Disable When or Hide When rule holds now: (True, the group
    that makes it hold), (False, None), or (None, None) when the rule has a form
    this reader does not know.

    Houdini writes the rule as groups in braces. A group holds when every term
    in it holds, and the rule holds when any group does.
    """
    unknown = False
    for group in re.findall(r"\{([^}]*)\}", rule) or [None]:
        terms = _TERM.findall(group or "")
        if not terms or _TERM.sub("", group).strip():
            unknown = True
            continue
        results = [_term_holds(node, *term) for term in terms]
        if None in results:
            unknown = True
        elif all(results):
            return True, "{ " + group.strip() + " }"
    return (None, None) if unknown else (False, None)


def state(parm):
    """Whether the cook reads this parameter now, and if not, why.

    A disabled or a hidden parameter keeps a value that the cook does not read,
    so a value that looks like live data is not. `hou.Parm.isDisabled` and
    `isHidden` answer only in a graphical session, so the rules are also read
    here, from the values of the parameters that they name. Returns a
    dictionary with "disabled" and "hidden" (the group of the rule that holds),
    or "disabled_when" and "hidden_when" (a rule this reader cannot decide).
    """
    found = {}
    template = parm.parmTemplate()
    try:
        conditionals = template.conditionals()
    except hou.OperationFailed:
        conditionals = {}
    for kind, key, asked in ((hou.parmCondType.DisableWhen, "disabled", "isDisabled"),
                             (hou.parmCondType.HideWhen, "hidden", "isHidden")):
        rule = conditionals.get(kind)
        try:
            shown = getattr(parm, asked)()
        except hou.OperationFailed:
            shown = False
        holds, group = _rule_holds(parm.node(), rule) if rule else (False, None)
        if shown or holds:
            found[key] = group or rule or "the node state"
        elif holds is None:
            found[f"{key}_when"] = rule
    if template.isHidden():
        found["hidden"] = "the parameter template, always"
    return found


def inert(parm):
    """True when the cook of the node does not read this parameter now."""
    found = state(parm)
    return "disabled" in found or "hidden" in found


def _state_warnings(found):
    """The sentences that say what `state` found."""
    lines = []
    if "disabled" in found:
        lines.append(f"the parameter is disabled while {found['disabled']} holds, so the "
                     f"cook does not read the value. Change that condition first.")
    if "hidden" in found:
        lines.append(f"the parameter is hidden while {found['hidden']} holds: the user "
                     f"cannot see it, and in this mode the node most likely does not "
                     f"read it.")
    for key, word in (("disabled_when", "disabled"), ("hidden_when", "hidden")):
        if key in found:
            lines.append(f"this parameter is {word} when {found[key]}, and this tool "
                         f"cannot decide that rule. Read the parameters that it names.")
    return lines


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
    found = state(parm)
    for key in ("disabled", "hidden"):
        if key in found:
            report[f"{key}_by"] = found[key]
    # An undecided rule matters where a value was written: a written value that
    # the cook ignores reads as live data. At the default it is only noise.
    if not report["is_at_default"]:
        report.update({key: found[key] for key in ("disabled_when", "hidden_when")
                       if key in found})
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
        bits = _bits(template)
        if bits:
            report["bit_field"] = bits
            report["bits_set"] = [token for token, bit in bits.items() if value & bit]
        elif isinstance(value, int) and 0 <= value < len(tokens):
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
    bits = _bits(template)
    if bits and isinstance(value, (str, list, tuple)):
        try:
            value = _bit_sum(bits, value)
        except ValueError as error:
            return {**report, "applied": False, "bit_field": bits, "reason": str(error)}
        report["bits"] = value

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
    warnings = []
    if target:
        report["wrote_to"] = target.path()
    clamped = _range_note(template, value, report["new"])
    if expression and not report["applied"]:
        report["expression"] = expression
        report["reason"] = ("the parameter carries an expression, which still decides the "
                            "value. Remove it with mode 'revert', or write the expression.")
    elif keyframes:
        report["keyframe_count"] = len(parm.keyframes())
        warnings.append("the parameter is animated: the value became a new key at this frame.")
    elif not report["applied"]:
        report["reason"] = clamped or _refused_reason(parm, template, tokens, value)
    elif clamped:
        warnings.append(clamped)

    found = state(parm)
    report.update({f"{key}_by": found[key] for key in ("disabled", "hidden") if key in found})
    warnings += write_notes(parm, target, found)
    if warnings:
        report["warnings"] = warnings
    return report


def _refused_reason(parm, template, tokens, value):
    """Why a value did not take, named from the template instead of guessed."""
    if tokens:
        return (f"'{value}' is not a token of this menu. Tokens: {', '.join(map(str, tokens))}. "
                f"The parameter holds {parm.rawValue()!r} now.")
    return (f"Houdini kept {parm.eval()!r} for a write of {value!r}. The parameter type is "
            f"{template.type().name()}.")


def _bit_sum(bits, value):
    """The number to store in a bit-field menu for a token, a list of tokens,
    or tokens in one text with spaces between them."""
    names = value.split() if isinstance(value, str) else list(value)
    unknown = [name for name in names if name not in bits]
    if unknown:
        raise ValueError(f"{', '.join(map(repr, unknown))} is not a token of this bit-field "
                         f"menu. It stores the sum of the bits of the chosen items: "
                         f"{bits}. Write a token, a list of tokens or a number.")
    return sum(bits[name] for name in set(names))


def _range_note(template, asked, now):
    """What a range did to a number that was written: the clamp of a strict
    range, or a value past the slider, which Houdini keeps. None when neither."""
    if not hasattr(template, "minValue") or isinstance(asked, bool) \
            or not isinstance(asked, (int, float)):
        return None
    low, high = template.minValue(), template.maxValue()
    if (template.minIsStrict() and asked < low) or (template.maxIsStrict() and asked > high):
        return (f"Houdini clamped {asked} to {now}: this parameter accepts only "
                f"{low} to {high}. Values past that end all give the same result.")
    if asked < low or asked > high:
        return (f"{asked} is past the slider range {low} to {high}. Houdini kept it, "
                f"because that range is only a slider limit, but the node was not tuned "
                f"for it.")
    return None


def write_notes(parm, target=None, found=None):
    """The warnings after a write to `parm` that the write itself cannot show:
    the node it really changed, a state that makes the cook ignore it, and
    text that Houdini expands."""
    notes = []
    if target:
        notes.append(f"the value went to {target.path()}, not to {parm.path()}, because "
                     f"this parameter reads it through a channel reference.")
    notes += _state_warnings(state(parm) if found is None else found)
    expanded = _expansion_warning(parm, parm.parmTemplate())
    if expanded:
        notes.append(expanded)
    return notes


def script_write_note(parm, value, target):
    """One line for a parameter that a script wrote in a way that changes
    nothing, or changes something else. None for a plain write. `target` is
    the parameter that a channel reference sent the write to, read before it."""
    template = parm.parmTemplate()
    notes = write_notes(parm, target)
    bits = _bits(template)
    if bits and isinstance(value, str):
        notes.append(f"this menu is a bit field, and Houdini stored {value!r} as the "
                     f"item index {parm.eval()}, not as its bit. Write the sum of the "
                     f"bits: {bits}.")
    range_note = _range_note(template, value, parm.eval())
    if range_note:
        notes.append(range_note)
    expression = _expression(parm)
    if expression and not target:
        notes.append(f"the parameter carries the expression {expression!r}, which "
                     f"still decides the value.")
    return f"{parm.path()}: " + " ".join(notes) if notes else None


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
    condition = state(parm).get("disabled")
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
        found = state(one)
        info.update({f"{key}_by": found[key] for key in ("disabled", "hidden")
                     if key in found})
        bits = _bits(template)
        if bits:
            info["bit_field"] = bits
        schema.append(info)
    return {"path": node_path, "count": len(schema), "parameters": schema}


def matches(parm, pattern):
    """True when the name or the label of `parm` matches `pattern`.

    `|` separates alternatives, for example "time|step|cfl". Each one is a
    glob or a part of the name or of the label, with no case.
    """
    if not pattern:
        return True
    name, label = parm.name().lower(), parm.parmTemplate().label().lower()
    return any(one and (fnmatch.fnmatch(name, one) or one in name or one in label)
               for one in (part.strip() for part in pattern.lower().split("|")))


def _selected_parms(node, parm=None, pattern=None):
    """The parameters that a caller asked for: one name, a pattern, or all."""
    if parm:
        one = node.parm(parm)
        if not one:
            raise ValueError(_no_such(node, parm))
        return [one]
    return [one for one in node.parms() if matches(one, pattern)]


# Templates that hold no value a person sets: they lay out the pane.
_LAYOUT = {"Folder", "FolderSet", "Label", "Separator", "Button"}


def _ramp_of(parm):
    """The ramp parameter that `parm` is a key of, or None."""
    parent = parm.parentMultiParm()
    return parent if parent and parent.parmTemplate().type() == hou.parmTemplateType.Ramp \
        else None


def _ramp_summary(parm):
    """One entry for a whole ramp: its keys, as (position, value) pairs."""
    ramp = parm.evalAsRamp()
    values = [tuple(round(part, 3) for part in value) if isinstance(value, tuple)
              else round(value, 3) for value in ramp.values()]
    return {"name": parm.name(), "label": parm.parmTemplate().label(), "type": "Ramp",
            "key_count": len(ramp.keys()),
            "keys": [[round(key, 3), value] for key, value in zip(ramp.keys(), values)][:12]}


def get_parameters(node_path, parm=None, pattern=None, has_expression=False,
                   changed_only=False, fields=None):
    """Read the parameters of a node, with a filter.

    `changed_only` keeps a parameter that is not at its default, that carries an
    expression, or that has keys. An expression usually sits on a parameter that
    is at its default value, so a filter on the value alone hides the part that
    makes a scene time dependent. It leaves out what a person does not set:
    folders, labels, buttons and parameters that the template hides. A ramp is
    one entry, not one entry for each key.

    `fields` keeps only these keys of each entry, for example
    ["value", "expression"]. The name is always kept.
    """
    node = _node(node_path)
    found, ramps = [], []
    for one in _selected_parms(node, parm, pattern):
        template = one.parmTemplate()
        if changed_only:
            if template.type().name() in _LAYOUT or template.isHidden():
                continue
            # A key of a ramp is not at its template default even when the
            # ramp is at the default of the node, so the ramp itself decides.
            if _ramp_of(one) is not None:
                continue
            if template.type() == hou.parmTemplateType.Ramp:
                if not one.isAtRampDefault():
                    ramps.append(one)
                continue
        expression = _expression(one)
        keys = one.keyframes() if not expression else ()
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
    if fields:
        found = [{key: report[key] for key in ["name", *fields] if key in report}
                 for report in found]
    found += [_ramp_summary(ramp) for ramp in ramps]
    return {"path": node_path, "count": len(found),
            "parameter_count": len(node.parms()), "parameters": found}


def readers(node_path, parm_name):
    """The parameters that read this one through a channel reference or an
    expression. A change here changes each of them."""
    node = _node(node_path)
    parm = node.parm(parm_name)
    if not parm:
        raise ValueError(_no_such(node, parm_name))
    found = [{"path": other.path(), "expression": _expression(other)}
             for other in parm.parmsReferencingThis() if other.path() != parm.path()]
    return {"path": node_path, "parm": parm_name, "count": len(found), "read_by": found}


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
