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


def set_parameter(node_path, parm_name, value):
    """Set a single parameter value."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parm = node.parm(parm_name)
    if not parm:
        raise ValueError(f"Parameter not found: {parm_name} on {node_path}")
    old_value = parm.eval()
    parm.set(value)
    return {"path": node_path, "parm": parm_name, "old_value": old_value, "new_value": parm.eval()}


def set_parameters(node_path, parameters):
    """Set multiple parameters at once."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    changes = []
    for parm_name, value in parameters.items():
        parm = node.parm(parm_name)
        if parm:
            old_value = parm.eval()
            parm.set(value)
            changes.append({"parm": parm_name, "old": old_value, "new": parm.eval()})
    return {"path": node_path, "changes": changes}


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
