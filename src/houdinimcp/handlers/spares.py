"""Spare parameters: the controls that a person tunes on a node.

A wrangle with its numbers typed into the VEX gives the user nothing to tune.
The code reads `chf("name")`, and the parameter must exist on the node, in the
place where a person looks for it: the folder that the Create Parameters
button makes, directly above the code.
"""
import hou

FOLDER = "folder_generatedparms_snippet"


def _template(spec):
    """The parameter template for one definition."""
    name = spec["name"]
    kind = spec.get("type", "float")
    label = spec.get("label") or name.replace("_", " ").title()
    default = spec.get("default")
    if kind in ("float", "int", "vector"):
        size = 3 if kind == "vector" else int(spec.get("size", 1))
        values = list(default) if isinstance(default, (list, tuple)) \
            else [default if default is not None else 0] * size
        ranged = {key: spec[key] for key in ("min", "max") if key in spec}
        if spec.get("strict"):
            ranged.update(min_is_strict="min" in spec, max_is_strict="max" in spec)
        make = hou.IntParmTemplate if kind == "int" else hou.FloatParmTemplate
        template = make(name, label, size, default_value=values, **ranged)
        if size > 1:
            template.setNamingScheme(hou.parmNamingScheme.XYZW)
    elif kind == "toggle":
        template = hou.ToggleParmTemplate(name, label, default_value=bool(default))
    elif kind == "string":
        template = hou.StringParmTemplate(name, label, 1,
                                          default_value=(str(default or ""),))
    elif kind == "menu":
        items = [str(item) for item in spec["items"]]
        template = hou.MenuParmTemplate(name, label, items,
                                        menu_labels=spec.get("labels") or items,
                                        default_value=items.index(default) if default else 0)
    elif kind in ("ramp", "color_ramp"):
        template = hou.RampParmTemplate(
            name, label,
            hou.rampParmType.Color if kind == "color_ramp" else hou.rampParmType.Float)
    else:
        raise ValueError(f"Unknown type '{kind}' for {name}. Use float, int, vector, toggle, "
                         f"string, menu, ramp or color_ramp.")
    if spec.get("help"):
        template.setHelp(spec["help"])
    return template


def _folder(group, snippet):
    """The folder of generated parameters above the code, made as the button
    makes it when it is not there yet."""
    folder = group.find(FOLDER)
    if folder is None:
        group.insertBefore(snippet, hou.FolderParmTemplate(
            FOLDER, "Generated Channel Parameters", folder_type=hou.folderType.Simple))
        folder = group.find(FOLDER)
    return folder


def _generated(node):
    """The names of the parameters in the folder of generated parameters."""
    folder = node.parmTemplateGroup().find(FOLDER)
    return [template.name() for template in folder.parmTemplates()] if folder else []


def _set(node, spec):
    """Write the value, the ramp keys or the expression of one definition."""
    parms = node.parmTuple(spec["name"])
    if spec.get("type") in ("ramp", "color_ramp") and spec.get("default"):
        keys = spec["default"]
        values = [tuple(value) if isinstance(value, list) else value for _, value in keys]
        parms[0].set(hou.Ramp([hou.rampBasis.Linear] * len(keys),
                              [position for position, _ in keys], values))
    if "value" in spec:
        value = spec["value"]
        parms.set(value if isinstance(value, (list, tuple)) else [value] * len(parms))
    if "expression" in spec:
        expressions = spec["expression"]
        language = getattr(hou.exprLanguage, spec.get("language", "hscript").capitalize())
        for parm, text in zip(parms, expressions if isinstance(expressions, list)
                              else [expressions] * len(parms)):
            parm.deleteAllKeyframes()
            parm.setExpression(text, language)


def add_spare_parameters(node_path, specs):
    """Add or replace spare parameters, and give each its value.

    On a node with VEX code, it first does what the Create Parameters button
    does, then puts each definition in that folder. A parameter that exists is
    replaced in place and keeps its value.
    """
    node = hou.node(node_path)
    if node is None:
        raise ValueError(f"Node not found: {node_path}")
    snippet = "snippet" if node.parm("snippet") is not None else None
    from_code = []
    if snippet:
        import vexpressionmenu
        before = _generated(node)
        vexpressionmenu.createSpareParmsFromChCalls(node, snippet)
        from_code = [name for name in _generated(node) if name not in before]
    group = node.parmTemplateGroup()
    made, replaced = [], []
    for spec in specs:
        template = _template(spec)
        if group.find(spec["name"]) is not None:
            group.replace(spec["name"], template)
            replaced.append(spec["name"])
        elif snippet:
            group.appendToFolder(_folder(group, snippet), template)
            made.append(spec["name"])
        else:
            group.append(template)
            made.append(spec["name"])
    node.setParmTemplateGroup(group)
    for spec in specs:
        _set(node, spec)

    report = {"path": node_path, "made": made, "replaced": replaced}
    if snippet:
        report["folder"] = FOLDER
    unset = [name for name in from_code if name not in {spec["name"] for spec in specs}]
    if unset:
        report["from_code"] = unset
        report["note"] = ("These parameters came from the ch() calls in the code, with a "
                          "label made from the name and a default of 0. Give them in "
                          "`parameters` to set the label, the default and the range.")
    try:
        node.cook(force=True)
    except hou.OperationFailed:
        pass   # the message is in node.errors()
    report["errors"] = list(node.errors())
    return report
