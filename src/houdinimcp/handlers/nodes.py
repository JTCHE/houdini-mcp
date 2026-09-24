"""Node CRUD, wiring, flags, layout, and material handlers."""
import re

import hou
from .parameters import inert, matches


def create_node(node_type, parent_path="/obj", name=None, position=None, parameters=None,
                input_path=None):
    """Make a node, place it, wire its first input, and write its parameters."""
    from . import parameters as parameters_handler

    parent = hou.node(parent_path)
    if not parent:
        raise ValueError(f"Parent path not found: {parent_path}")
    try:
        node = parent.createNode(node_type, node_name=name)
    except hou.OperationFailed as error:
        raise ValueError(f"Houdini has no node type '{node_type}' in {parent_path}: {error}. "
                         f"Read the type name with scene_overview mode 'node_types'.") from error

    report = {"name": node.name(), "path": node.path(), "type": node.type().name()}
    if name and node.name() != name:
        report["renamed_by_houdini"] = (f"The name '{name}' was in use. Use the path in this "
                                        f"result from now on.")
    if input_path:
        source = hou.node(input_path)
        if not source:
            raise ValueError(f"Input node not found: {input_path}")
        node.setInput(0, source)
        report["input"] = source.path()
    if position and len(position) >= 2:
        node.setPosition([position[0], position[1]])
    else:
        place_node(node)
    report["position"] = list(node.position())
    if parameters:
        # The same write path as parm_set, so a write that does nothing is
        # reported here too instead of passing for success.
        written = parameters_handler.set_parameters(node.path(), parameters)
        report["parameters"] = written["changes"]
        if written["not_applied"]:
            report["not_applied"] = written["not_applied"]
    return report


def modify_node(path, parameters=None, position=None, name=None):
    """Modifies an existing node."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")

    changes = []
    old_name = node.name()

    if name and name != old_name:
        node.setName(name)
        changes.append(f"Renamed from {old_name} to {name}")

    if position and len(position) >= 2:
        node.setPosition([position[0], position[1]])
        changes.append(f"Position set to {position}")

    if parameters:
        for p_name, p_val in parameters.items():
            parm = node.parm(p_name)
            if parm:
                old_val = parm.eval()
                parm.set(p_val)
                changes.append(f"Parameter {p_name} changed from {old_val} to {p_val}")

    return {"path": node.path(), "changes": changes}


def delete_node(path):
    """Deletes a node from the scene."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    node_path = node.path()
    node_name = node.name()
    node.destroy()
    return {"deleted": node_path, "name": node_name}


def _parm_default_value(parm):
    """Return the default scalar value for one parm component, or None on failure."""
    try:
        defaults = parm.parmTemplate().defaultValue()
        if isinstance(defaults, (tuple, list)):
            idx = parm.componentIndex()
            return defaults[idx] if idx < len(defaults) else (defaults[0] if defaults else None)
        return defaults
    except Exception:
        return None


def _menu_label(template, val):
    """Map a menu parm's value to its label, or None if the parm has no menu.

    Handles both integer-indexed menus (Int/Menu templates, eval -> index) and
    string-token menus (String templates, eval -> token).
    """
    try:
        labels = template.menuLabels()
        if not labels:
            return None
        if isinstance(val, bool):
            return None
        if isinstance(val, (int, float)):
            idx = int(val)
            if 0 <= idx < len(labels):
                return labels[idx]
            return None
        if isinstance(val, str):
            items = template.menuItems()
            if items and val in items:
                return labels[items.index(val)]
    except Exception:
        pass
    return None


def get_node_info(path, include_all_parms=False):
    """Returns detailed information about a node.

    By default only changed parameters are returned (token-lean).
    Pass include_all_parms=True for the full parameter table.
    """
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")

    node_type = node.type()
    color = node.color()

    node_info = {
        "name": node.name(),
        "path": node.path(),
        "type": node_type.name(),
        "type_label": node_type.description(),
        "category": node_type.category().name(),
        "position": [node.position()[0], node.position()[1]],
        "color": list(color.rgb()),
        "is_bypassed": getattr(node, "isBypassed", lambda: None)(),
        "is_displayed": getattr(node, "isDisplayFlagSet", lambda: None)(),
        "is_rendered": getattr(node, "isRenderFlagSet", lambda: None)(),
        "inputs": [],
        "outputs": [],
    }

    changed = []
    unchanged_count = 0

    for parm in node.parms():
        template = parm.parmTemplate()
        ptype = template.type()
        is_at_default = parm.isAtDefault()

        if is_at_default and not include_all_parms:
            unchanged_count += 1
            continue

        try:
            val = parm.eval()
        except Exception:
            val = parm.rawValue()

        entry = {
            "id": parm.name(),
            "label": template.label(),
            "value": str(val),
            "type": ptype.name(),
        }

        # Resolve a human-readable label for menu parms (returns None if not a menu)
        lbl = _menu_label(template, val)
        if lbl is not None:
            entry["value_label"] = lbl

        if not is_at_default:
            default = _parm_default_value(parm)
            if default is not None:
                entry["default"] = str(default)
                dlbl = _menu_label(template, default)
                if dlbl is not None:
                    entry["default_label"] = dlbl

        changed.append(entry)

    node_info["changed_parameters"] = changed
    node_info["parameter_count"] = len(node.parms())
    node_info["unchanged_count"] = unchanged_count

    for i, in_node in enumerate(node.inputs()):
        if in_node:
            node_info["inputs"].append({
                "index": i,
                "name": in_node.name(),
                "path": in_node.path(),
                "type": in_node.type().name(),
            })

    for out_conn in node.outputConnections():
        out_node = out_conn.outputNode()
        node_info["outputs"].append({
            "name": out_node.name(),
            "path": out_node.path(),
            "type": out_node.type().name(),
            "input_index": out_conn.inputIndex(),
        })

    return node_info


def get_changed_parms(path):
    """Return only changed parameters for a node — the cheapest 'what did I tweak' call."""
    info = get_node_info(path)
    return {
        "path": path,
        "changed_parameters": info["changed_parameters"],
        "parameter_count": info["parameter_count"],
        "unchanged_count": info["unchanged_count"],
    }


def get_node_doc_meta(path):
    """Return type/category/defaultHelpUrl for a node so the bridge can fetch its docs."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    node_type = node.type()
    try:
        help_url = node_type.defaultHelpUrl()
    except Exception:
        help_url = None
    return {
        "type_name": node_type.name(),
        "category": node_type.category().name(),
        "default_help_url": help_url,
    }


def connect_nodes(src_path, dst_path, dst_input_index=0, src_output_index=0):
    """Connect two nodes: src output -> dst input."""
    src = hou.node(src_path)
    dst = hou.node(dst_path)
    if not src:
        raise ValueError(f"Source node not found: {src_path}")
    if not dst:
        raise ValueError(f"Destination node not found: {dst_path}")
    dst.setInput(dst_input_index, src, src_output_index)
    return {
        "connected": True,
        "src": src.path(),
        "dst": dst.path(),
        "dst_input": dst_input_index,
        "src_output": src_output_index,
    }


def disconnect_node_input(node_path, input_index=0):
    """Disconnect a specific input on a node."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    node.setInput(input_index, None)
    return {"disconnected": True, "node": node.path(), "input_index": input_index}


def set_node_flags(node_path, display=None, render=None, bypass=None):
    """Set display, render, and/or bypass flags on a node."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    changes = []
    if display is not None:
        node.setDisplayFlag(display)
        changes.append(f"display={display}")
    if render is not None:
        node.setRenderFlag(render)
        changes.append(f"render={render}")
    if bypass is not None:
        node.bypass(bypass)
        changes.append(f"bypass={bypass}")
    return {"path": node.path(), "changes": changes}


def layout_children(node_path="/obj", paths=None):
    """Tidy the nodes of a network.

    `paths` names the nodes to move. Without it every node in the network
    moves, and the positions that a person set by hand are lost: only do that
    when the user asked for it.
    """
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    if paths:
        items = []
        for path in paths:
            child = hou.node(path)
            if not child:
                raise ValueError(f"Node not found: {path}")
            items.append(child)
        node.layoutChildren(items=items)
        return {"path": node.path(), "laid_out": [item.path() for item in items]}
    node.layoutChildren()
    return {"path": node.path(), "laid_out": "every node in this network",
            "warning": "Every node moved, and that includes the nodes that the user "
                       "placed by hand. Give `paths` to move only your own nodes."}


def place_node(node):
    """Put one new node in a free place near its input, and move nothing else.

    Houdini's own layout moves every node in the network. A new node that
    places itself removes the reason to call that.
    """
    try:
        node.moveToGoodPosition(relative_to_inputs=True, move_inputs=False,
                                move_outputs=False, move_unconnected=False)
    except (hou.OperationFailed, AttributeError):
        pass
    return list(node.position())


def set_node_color(node_path, color):
    """Set a node's color as [r, g, b] (0-1 range)."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    if len(color) != 3:
        raise ValueError(f"Color must be [r, g, b], got: {color}")
    node.setColor(hou.Color(color[0], color[1], color[2]))
    return {"path": node.path(), "color": color}


def set_material(node_path, material_type="principledshader", name=None, parameters=None):
    """Creates or applies a material to an OBJ node."""
    target_node = hou.node(node_path)
    if not target_node:
        raise ValueError(f"Node not found: {node_path}")

    if target_node.type().category().name() != "Object":
        raise ValueError(
            f"Node {node_path} is not an OBJ-level node and cannot accept direct materials."
        )

    mat_context = hou.node("/mat")
    if not mat_context:
        mat_context = hou.node("/shop")
        if not mat_context:
            raise RuntimeError("No /mat or /shop context found to create materials.")

    mat_name = name or (f"{material_type}_auto")
    mat_node = mat_context.node(mat_name)
    if not mat_node:
        mat_node = mat_context.createNode(material_type, mat_name)

    if parameters:
        for k, v in parameters.items():
            p = mat_node.parm(k)
            if p:
                p.set(v)

    mat_parm = target_node.parm("shop_materialpath")
    if mat_parm:
        mat_parm.set(mat_node.path())
    else:
        geo_sop = target_node.node("geometry")
        if not geo_sop:
            raise RuntimeError("No 'geometry' node found inside OBJ to apply material to.")

        material_sop = geo_sop.node("material1")
        if not material_sop:
            material_sop = geo_sop.createNode("material", "material1")
            first_sop = None
            for c in geo_sop.children():
                if c.isDisplayFlagSet():
                    first_sop = c
                    break
            if first_sop:
                material_sop.setFirstInput(first_sop)
            material_sop.setDisplayFlag(True)
            material_sop.setRenderFlag(True)

        mat_sop_parm = material_sop.parm("shop_materialpath1")
        if mat_sop_parm:
            mat_sop_parm.set(mat_node.path())
        else:
            raise RuntimeError(
                "No shop_materialpath1 on Material SOP to assign the material."
            )

    return {
        "status": "ok",
        "material_node": mat_node.path(),
        "applied_to": target_node.path(),
    }


def set_expression(node_path, parm_name, expression, language="hscript"):
    """Set an expression on a node parameter."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parm = node.parm(parm_name)
    if not parm:
        raise ValueError(f"Parameter not found: {parm_name} on {node_path}")
    lang = hou.exprLanguage.Hscript if language == "hscript" else hou.exprLanguage.Python
    parm.setExpression(expression, lang)
    return {
        "path": node.path(),
        "parm": parm_name,
        "expression": expression,
        "language": language,
    }


def copy_node(path, destination_path):
    """Copy a node to a new parent."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    dest = hou.node(destination_path)
    if not dest:
        raise ValueError(f"Destination not found: {destination_path}")
    items = hou.copyNodesTo([node], dest)
    new_node = items[0]
    return {"path": new_node.path(), "name": new_node.name(), "type": new_node.type().name()}


def move_node(path, destination_path):
    """Move a node to a new parent."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    dest = hou.node(destination_path)
    if not dest:
        raise ValueError(f"Destination not found: {destination_path}")
    items = hou.moveNodesTo([node], dest)
    new_node = items[0]
    return {"path": new_node.path(), "name": new_node.name(), "type": new_node.type().name()}


def rename_node(path, new_name):
    """Rename a node."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    old_name = node.name()
    node.setName(new_name)
    return {"old_name": old_name, "new_name": node.name(), "path": node.path()}


def list_children(path, recursive=False):
    """List all children of a node."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    if recursive:
        children = node.allSubChildren()
    else:
        children = node.children()
    nodes = []
    for child in children:
        nodes.append({
            "name": child.name(),
            "path": child.path(),
            "type": child.type().name(),
        })
    return {"path": path, "count": len(nodes), "children": nodes}


def find_nodes(pattern, node_type=None, root_path="/"):
    """Find nodes matching a name pattern, optionally filtered by type."""
    root = hou.node(root_path)
    if not root:
        raise ValueError(f"Root not found: {root_path}")
    matches = root.glob(pattern)
    nodes = []
    for n in matches:
        if node_type and n.type().name() != node_type:
            continue
        nodes.append({
            "name": n.name(),
            "path": n.path(),
            "type": n.type().name(),
        })
    return {"pattern": pattern, "count": len(nodes), "nodes": nodes}


def list_node_types(category=None):
    """List available node types, optionally filtered by category."""
    result = []
    for cat_name, cat in hou.nodeTypeCategories().items():
        if category and cat_name != category:
            continue
        for name, nt in cat.nodeTypes().items():
            result.append({
                "name": name,
                "category": cat_name,
                "label": nt.description(),
            })
        if len(result) >= 500:
            break
    return {"count": len(result), "types": result}


def connect_nodes_batch(connections):
    """Connect multiple node pairs at once.

    connections: list of dicts with src_path, dst_path, dst_input_index, src_output_index
    """
    results = []
    for conn in connections:
        src = hou.node(conn["src_path"])
        dst = hou.node(conn["dst_path"])
        if not src:
            raise ValueError(f"Source not found: {conn['src_path']}")
        if not dst:
            raise ValueError(f"Destination not found: {conn['dst_path']}")
        dst.setInput(conn.get("dst_input_index", 0), src, conn.get("src_output_index", 0))
        results.append({
            "src": src.path(), "dst": dst.path(),
            "dst_input": conn.get("dst_input_index", 0),
        })
    return {"connected": len(results), "connections": results}


def reorder_inputs(path, input_indices):
    """Reorder the inputs of a node by specifying the new index order."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    current_inputs = list(node.inputs())
    new_inputs = []
    for idx in input_indices:
        if idx is not None and idx < len(current_inputs):
            new_inputs.append(current_inputs[idx])
        else:
            new_inputs.append(None)
    for i, inp in enumerate(new_inputs):
        node.setInput(i, inp)
    return {"path": node.path(), "new_order": input_indices}


def name_parameters(path, pattern=None):
    """The names and labels of the parameters of a node, and nothing else.

    The cheapest answer to "what is this parameter called". A full read of a
    solver has hundreds of thousands of characters and a client drops it.
    """
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    found = []
    for parm in node.parms():
        if not matches(parm, pattern):
            continue
        found.append({"name": parm.name(), "label": parm.parmTemplate().label(),
                      "type": parm.parmTemplate().type().name()})
    return {"path": path, "count": len(found), "parameters": found}


def _known_names(node):
    """Every name that the geometry at a node's inputs really carries.

    A parameter that names an attribute, a group or a volume field turns its
    feature off in silence when the name matches nothing, so the list of names
    that do exist is what a caller needs to see.
    """
    names = {"attributes": set(), "groups": set(), "volumes": set()}
    # The node itself as well as its inputs: a solver SOP names the fields of
    # the simulation it makes, and those fields are not at its input.
    sources = [source for source in node.inputs() if source] + [node]
    for source in sources:
        try:
            geometry = source.geometry()
        except (hou.OperationFailed, AttributeError):
            continue
        if not geometry:
            continue
        for attribute in (list(geometry.pointAttribs()) + list(geometry.primAttribs())
                          + list(geometry.globalAttribs()) + list(geometry.vertexAttribs())):
            names["attributes"].add(attribute.name())
        for group in list(geometry.pointGroups()) + list(geometry.primGroups()):
            names["groups"].add(group.name())
        # A volume or a VDB carries its field name in the `name` primitive
        # attribute, which is also how a solver parameter names a field.
        if geometry.findPrimAttrib("name"):
            names["volumes"].update(geometry.primStringAttribValues("name"))
    return {kind: sorted(value) for kind, value in names.items()}


def _class_fixes(node):
    """Parameters that name an attribute without the class prefix it needs.

    Some nodes read "point.v", not "v". With the bare name they cook with no
    error, skip the attribute, and say so only in a warning.
    """
    fixes = []
    for warning in node.warnings():
        found = re.search(r"unrecognized class.*:\s*(\S+)\s*$", warning)
        if not found:
            continue
        name = found.group(1)
        classes = [kind for kind, find in (("point", "findPointAttrib"),
                                           ("vertex", "findVertexAttrib"),
                                           ("prim", "findPrimAttrib"))
                   if any(getattr(source.geometry(), find)(name)
                          for source in node.inputs() if source and source.geometry())]
        for parm in node.parms():
            if parm.parmTemplate().type() == hou.parmTemplateType.String                     and parm.evalAsString() == name:
                fixes.append({"parm": parm.name(), "value": name,
                              "write": f"{classes[0]}.{name}" if classes else None,
                              "why": f"the node needs the class before the name. It said: "
                                     f"{warning}" + ("" if classes else
                                                     f" No input carries {name}.")})
    return fixes


def validate_names(path):
    """Find parameters that name an attribute, group or field that does not exist.

    Houdini does not report this. The feature that reads the name simply does
    nothing, the node cooks with no error, and the result is wrong in a way
    that looks like a wrong choice of tool.
    """
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    known = _known_names(node)
    every = set(known["attributes"]) | set(known["groups"]) | set(known["volumes"])
    unmatched = []
    for parm in node.parms():
        if parm.parmTemplate().type() != hou.parmTemplateType.String:
            continue
        if parm.isAtDefault() or inert(parm):
            continue
        try:
            value = parm.eval()
        except hou.OperationFailed:
            continue
        # Only a bare name can be an attribute, a group or a field. A path, a
        # pattern or an expression is something else.
        if not value or not value.replace("_", "").isalnum() or value == node.name():
            continue
        if value in every:
            continue
        unmatched.append({"parm": parm.name(), "label": parm.parmTemplate().label(),
                          "value": value})
    report = {"path": path}
    fixes = _class_fixes(node)
    if fixes:
        # First in the answer: a node warning inside a long report reads as a
        # broken node, when the fix is one value.
        report["fix_first"] = fixes
    return {
        **report,
        "reads_geometry_from": [one.path() for one in node.inputs() if one],
        "names_nothing": unmatched,
        "available": known,
        "note": ("Each parameter in names_nothing holds a bare name that no attribute, "
                 "group or volume of the input geometry carries. Houdini reports nothing "
                 "for this: the feature that reads the name does nothing. Confirm each "
                 "one against `available` before you change it; a name can also belong to "
                 "geometry that another input or a later frame makes."),
    }


# Marks in the text of a parameter that make a node cook again every frame.
TIME_MARKS = ("$F", "$T", "$SF", "frame()", "time()", "$FF")

# Parameters that make a node time dependent by their value, not by an
# expression. A LOP Import set to "Animated" is the common one.
TIME_PARMS = ("timesample", "importtime", "sample_behavior", "timedependent",
              "cacheframe", "motionblur")


def _why_time_dependent(node):
    """The parameters and the inputs that make this node cook on every frame."""
    causes = []
    for parm in node.parms():
        expression = None
        try:
            expression = parm.expression()
        except hou.OperationFailed:
            pass
        raw = parm.rawValue()
        text = expression or (raw if isinstance(raw, str) else "")
        if any(mark in text for mark in TIME_MARKS):
            causes.append({"parm": parm.name(), "value": _short(text, 200)})
        elif parm.name() in TIME_PARMS and parm.eval():
            causes.append({"parm": parm.name(), "value": parm.eval()})
    upstream = []
    for other in node.inputs():
        try:
            if other is not None and other.isTimeDependent():
                upstream.append(other.path())
        except (AttributeError, hou.OperationFailed):
            continue
    return causes, upstream


def time_dependency(path, frames=None, limit=40):
    """Which nodes cook again on every frame, why they do, and what each costs.

    Playback is slow because of a small number of nodes. This names them, says
    what makes each one time dependent, and, with `frames`, times each one and
    sorts the answer by the time it takes. A node with no reason of its own
    takes it from an input, and the input is named.
    """
    from . import timing

    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    dependent = []
    for child in [node] + list(node.allSubChildren()):
        try:
            if not child.isTimeDependent():
                continue
        except (AttributeError, hou.OperationFailed):
            continue
        causes, upstream = _why_time_dependent(child)
        dependent.append({"path": child.path(), "type": child.type().name(),
                          "time_dependent_parms": causes,
                          "time_dependent_inputs": upstream})

    report = {"path": path, "count": len(dependent)}
    if frames:
        # Time each one on its own: the sum over a chain says nothing about
        # which node in it is the slow one.
        for row in dependent[:limit]:
            target = hou.node(row["path"])
            if not target:
                continue
            timed = timing.cook_over([target], frames)
            row["mean_seconds"] = timed["mean_seconds"]
            row["total_seconds"] = timed["total_seconds"]
            if timed["errors"]:
                row["errors"] = timed["errors"]
        dependent.sort(key=lambda row: row.get("mean_seconds", 0), reverse=True)
        if len(dependent) > limit:
            report["not_timed"] = (f"{len(dependent) - limit} more nodes are time "
                                   f"dependent and were not timed. Raise limit, or "
                                   f"give a path deeper in the scene.")
    report["time_dependent"] = dependent
    return report


def find_error_nodes(root_path="/obj", limit=20, message_chars=600):
    """The nodes under a root that hold an error or a warning.

    Errors come first: a scene with a hundred warnings would otherwise push the
    one error that matters out of the answer. Long messages are cut, and the
    report says how many nodes it did not return.
    """
    root = hou.node(root_path)
    if not root:
        raise ValueError(f"Root node not found: {root_path}")
    bad, warned = [], []
    for node in root.allSubChildren():
        try:
            errors, warnings = node.errors(), node.warnings()
        except hou.OperationFailed:
            continue
        if errors:
            bad.append({"path": node.path(), "type": node.type().name(),
                        "errors": [_short(text, message_chars) for text in errors]})
        elif warnings:
            warned.append({"path": node.path(), "type": node.type().name(),
                           "warnings": [_short(text, message_chars) for text in warnings]})
    found = bad + warned
    report = {"root": root_path, "error_count": len(bad),
              "warning_count": len(warned), "nodes": found[:limit]}
    if len(found) > limit:
        report["not_returned"] = (f"{len(found) - limit} more nodes hold an error or a "
                                  f"warning. Raise limit, or give a root_path deeper "
                                  f"in the scene.")
    return report


def _short(text, most):
    """A message cut to a length a reader can take in."""
    text = text or ""
    return text if len(text) <= most else text[:most] + f" ... [{len(text)} chars]"
