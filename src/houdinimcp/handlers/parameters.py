"""Parameter read/write handlers."""
import hou


def get_parameter(node_path, parm_name):
    """Get a single parameter's value and metadata."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parm = node.parm(parm_name)
    if not parm:
        raise ValueError(f"Parameter not found: {parm_name} on {node_path}")
    template = parm.parmTemplate()
    result = {
        "name": parm.name(),
        "label": parm.parmTemplate().label(),
        "value": parm.eval(),
        "raw_value": parm.rawValue(),
        "type": template.type().name(),
        "is_at_default": parm.isAtDefault(),
        "is_locked": parm.isLocked(),
    }
    try:
        result["expression"] = parm.expression()
        result["expression_language"] = str(parm.expressionLanguage())
    except hou.OperationFailed:
        result["expression"] = None
    return result


def _write(node, parm_name, value):
    """Write one parameter and report what really happened.

    Houdini keeps a parameter that carries an expression: the write is accepted
    and the value does not change. A keyframed parameter takes the value as a
    new key. Both look like success to the caller, so the result says which
    happened and whether the value took.
    """
    parm = node.parm(parm_name)
    if not parm:
        return {"parm": parm_name, "applied": False, "reason": "no such parameter"}
    report = {"parm": parm_name, "old": parm.eval()}
    expression = None
    try:
        expression = parm.expression()
    except hou.OperationFailed:
        pass
    keyframes = parm.keyframes()
    try:
        parm.set(value)
    except hou.PermissionError as error:
        return {**report, "applied": False, "reason": f"locked: {error}"}
    report["new"] = parm.eval()
    report["applied"] = report["new"] == value
    if expression:
        report["expression"] = expression
        report["reason"] = ("the parameter carries an expression, which still decides the "
                            "value. Remove it with mode 'revert', or write the expression.")
    elif keyframes:
        report["keyframes"] = len(parm.keyframes())
        report["reason"] = "the parameter is animated: the value became a new key."
    elif not report["applied"]:
        report["reason"] = "Houdini kept another value. The parameter may be a menu or a range."
    return report


def set_parameter(node_path, parm_name, value):
    """Set a single parameter value."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    report = _write(node, parm_name, value)
    if report.get("reason") == "no such parameter":
        raise ValueError(f"Parameter not found: {parm_name} on {node_path}")
    return {"path": node_path, **report}


def set_parameters(node_path, parameters):
    """Set several parameters. Names that do not exist come back in the result."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    changes = [_write(node, name, value) for name, value in parameters.items()]
    return {
        "path": node_path,
        "changes": changes,
        "not_applied": [change["parm"] for change in changes if not change["applied"]],
    }


def get_parameter_schema(node_path):
    """Get the full parameter schema (all parm templates) for a node."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parms = []
    for parm in node.parms():
        template = parm.parmTemplate()
        info = {
            "name": parm.name(),
            "label": template.label(),
            "type": template.type().name(),
            "is_at_default": parm.isAtDefault(),
        }
        if hasattr(template, "menuItems"):
            items = template.menuItems()
            labels = template.menuLabels()
            if items:
                info["menu_items"] = list(items)
                info["menu_labels"] = list(labels)
        if hasattr(template, "minValue"):
            info["min"] = template.minValue()
            info["max"] = template.maxValue()
        parms.append(info)
    return {"path": node_path, "parameters": parms}


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
