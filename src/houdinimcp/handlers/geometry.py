"""Geometry inspection and export handlers.

Every read comes through `resolve`. A node with no geometry is almost never a
node that has no geometry: it is a node that failed to cook, and Houdini keeps
the reason in `node.errors()` and in `node.warnings()`. The one thing a caller
cannot work with is an empty result and no message.
"""
import os
import tempfile

import hou

from . import match

# The output of a node that `resolve` reads, by path. A KineFX import puts the
# mesh on output 0 and the skeletons on 1 and 2. The tool sets it for the
# duration of one call.
OUTPUTS = {}


def messages(node):
    """What the node itself reports. A warning is as important as an error: a
    File SOP that cannot read its file only warns, and it cooks empty."""
    return {"errors": list(node.errors()), "warnings": list(node.warnings())}


def failure(node, most=20):
    """Every node that holds an error where a failed cook of `node` can come
    from: the node, the nodes upstream of it, and the nodes inside it. A
    solver often fails on a node that one of its parameters names, and
    hou.OperationFailed says only "Error while cooking"."""
    found = []
    for other in [node] + list(node.inputAncestors()) + list(node.allSubChildren()):
        try:
            told = messages(other)
        except hou.OperationFailed:
            continue
        if told["errors"] or (other == node and told["warnings"]):
            found.append({"path": other.path(), "type": other.type().name(), **told})
    return found[:most]


def resolve(node_path, frame=None):
    """The node and its geometry, cooked, with the node's own reason on failure.

    `frame` reads the geometry at another frame and does not move the playbar,
    so a read never changes the frame that the user works on.
    """
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    if not hasattr(node, "geometry"):
        raise ValueError(f"{node_path} is a {node.type().category().name()} node, and it "
                         f"makes no geometry. Read a SOP node, or read a LOP stage with "
                         f"stage_inspect.")
    index = OUTPUTS.get(node_path, 0)
    count = len(node.outputNames()) if hasattr(node, "outputNames") else 1
    if index >= max(count, 1):
        raise ValueError(f"{node_path} has {count} outputs, so output {index} does not "
                         f"exist. Outputs: {_output_names(node)}.")
    try:
        geometry = (node.geometryAtFrame(frame, index) if frame is not None
                    else node.geometry(index))
    except hou.OperationFailed as error:
        raise ValueError(f"{node_path} did not cook: {error}. "
                         f"Nodes that report an error: {failure(node)}") from error
    if geometry is None:
        told = messages(node)
        raise ValueError(
            f"{node_path} produced no geometry. This is almost always a cook that failed. "
            f"errors={told['errors'] or 'none'} warnings={told['warnings'] or 'none'}")
    return node, geometry


def _with_messages(node, geometry, report):
    """Add the node's messages when the result is empty.

    Empty and silent is the one answer a caller cannot act on, and an empty
    File Cache usually carries its reason in a warning, not in an error.
    """
    if len(geometry.points()) or len(geometry.prims()):
        return report
    told = messages(node)
    return {**report, **told, "note": (
        "This node cooked and made nothing. Read errors and warnings above: a File SOP "
        "that cannot open its file only warns, and a Reload Geometry press fixes it."
        if told["errors"] or told["warnings"] else
        "This node cooked, made nothing, and reported nothing. Look upstream: the node "
        "before it, a group that matches no element, or a frame outside the range.")}


def get_geo_summary(node_path, frame=None):
    """Counts, attributes, groups and bounds. The first read of any node."""
    node, geo = resolve(node_path, frame)
    bbox = geo.boundingBox()
    report = {
        "path": node_path,
        "num_points": len(geo.points()),
        "num_prims": len(geo.prims()),
        "num_vertices": geo.intrinsicValue("vertexcount"),
        "bounding_box": {
            "min": list(bbox.minvec()),
            "max": list(bbox.maxvec()),
        },
        "point_attribs": [attribute_line(a) for a in geo.pointAttribs()],
        "prim_attribs": [attribute_line(a) for a in geo.primAttribs()],
        "vertex_attribs": [attribute_line(a) for a in geo.vertexAttribs()],
        "detail_attribs": [attribute_line(a) for a in geo.globalAttribs()],
        "point_groups": [group.name() for group in geo.pointGroups()],
        "prim_groups": [group.name() for group in geo.primGroups()],
    }
    volumes = volume_names(geo)
    if volumes:
        report["volumes"] = volumes
    if len(node.outputNames()) > 1:
        report["outputs"] = _output_names(node)
        report["output_read"] = OUTPUTS.get(node_path, 0)
    return _with_messages(node, geo, report)


def _output_names(node):
    """Each output of a node: its index, its label, and its point count."""
    found = []
    for index, label in enumerate(node.outputNames()):
        try:
            geometry = node.geometry(index)
            points = len(geometry.points()) if geometry is not None else None
        except hou.Error:
            points = None
        found.append({"output": index, "label": node.outputLabels()[index]
                      if index < len(node.outputLabels()) else label, "points": points})
    return found


def attribute_line(attribute):
    """An attribute as one short string: 'P (float3)'."""
    size = attribute.size()
    kind = attribute.dataType().name().lower()
    return f"{attribute.name()} ({kind}{size if size > 1 else ''})"


def volume_primitives(geometry):
    """The volume and VDB primitives of a geometry.

    A walk over every primitive in Python is slow on a heavy mesh, and a
    geometry that holds volumes never holds many primitives, so a large one is
    not scanned at all.
    """
    if len(geometry.prims()) > 5000:
        return []
    return [prim for prim in geometry.prims() if isinstance(prim, (hou.Volume, hou.VDB))]


def volume_names(geometry):
    """The names of the volume and VDB primitives, which is how a solver
    parameter names a field."""
    named = geometry.findPrimAttrib("name")
    return sorted({prim.attribValue("name") if named else ""
                   for prim in volume_primitives(geometry)})


def get_points(node_path, start=0, count=100, attribs=None, frame=None):
    """Get point data with pagination. Returns positions and optional attrib values."""
    node, geo = resolve(node_path, frame)
    points = geo.points()
    total = len(points)
    end = min(start + count, total)
    result_points = []
    for i in range(start, end):
        pt = points[i]
        pt_data = {"num": pt.number(), "pos": list(pt.position())}
        if attribs:
            for attr_name in attribs:
                attr = geo.findPointAttrib(attr_name)
                if attr:
                    pt_data[attr_name] = pt.attribValue(attr)
        result_points.append(pt_data)
    return {"total": total, "start": start, "count": len(result_points), "points": result_points}


def get_prims(node_path, start=0, count=100, attribs=None, frame=None):
    """Get primitive data with pagination."""
    node, geo = resolve(node_path, frame)
    prims = geo.prims()
    total = len(prims)
    end = min(start + count, total)
    result_prims = []
    for i in range(start, end):
        pr = prims[i]
        pr_data = {
            "num": pr.number(),
            "type": str(pr.type()),
            "vertex_count": pr.numVertices(),
        }
        if attribs:
            for attr_name in attribs:
                attr = geo.findPrimAttrib(attr_name)
                if attr:
                    pr_data[attr_name] = pr.attribValue(attr)
        result_prims.append(pr_data)
    return {"total": total, "start": start, "count": len(result_prims), "prims": result_prims}


def get_attrib_values(node_path, attrib_name, attrib_class="point", frame=None,
                      unique=False, start=0, count=10):
    """The values of one attribute.

    `unique` returns each value that occurs and how many elements carry it,
    which is the answer to "what pieces are in this geometry". Without it a
    numeric attribute comes back as its stats over every element, and at most
    `count` values from `start`: a full read of a large mesh is too big for a
    client to hold.
    """
    node, geo = resolve(node_path, frame)
    return attrib_values(geo, attrib_name, attrib_class, unique, start, count)


def attrib_values(geo, attrib_name, attrib_class="point", unique=False, start=0, count=10):
    """get_attrib_values on a geometry that no node holds."""
    if attrib_class == "detail":
        attribute = geo.findGlobalAttrib(attrib_name)
        if not attribute:
            raise ValueError(_no_attrib(geo, attrib_name, "detail"))
        return {"attrib": attrib_name, "class": "detail",
                "value": geo.attribValue(attrib_name)}

    finders = {
        "point": (geo.findPointAttrib, geo.pointFloatAttribValues,
                  geo.pointIntAttribValues, geo.pointStringAttribValues),
        "prim": (geo.findPrimAttrib, geo.primFloatAttribValues,
                 geo.primIntAttribValues, geo.primStringAttribValues),
        "vertex": (geo.findVertexAttrib, geo.vertexFloatAttribValues,
                   geo.vertexIntAttribValues, geo.vertexStringAttribValues),
    }.get(attrib_class)
    if not finders:
        raise ValueError(f"Unknown attribute class: {attrib_class}. "
                         f"Use point, prim, vertex or detail.")
    attribute = finders[0](attrib_name)
    if not attribute:
        raise ValueError(_no_attrib(geo, attrib_name, attrib_class))

    data_type = attribute.dataType().name()
    flat = list(finders[1 if "Float" in data_type else 2 if "Int" in data_type else 3](attrib_name))
    size = attribute.size()
    # Houdini returns one flat array. A vector attribute on 100 points arrives
    # as 300 numbers, and a caller cannot tell where one element ends.
    values = flat if size == 1 else [tuple(flat[index:index + size])
                                     for index in range(0, len(flat), size)]
    report = {"attrib": attrib_name, "class": attrib_class, "type": data_type,
              "tuple_size": size, "element_count": len(values)}
    if unique:
        counts = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        ordered = sorted(counts.items(), key=lambda pair: -pair[1])[:count]
        report["unique_count"] = len(counts)
        report["unique"] = [{"value": value, "elements": number} for value, number in ordered]
        return report
    if values and "String" not in data_type:
        report["stats"] = _stats(values, size)
    window = values[start:start + count]
    report.update({"start": start, "returned": len(window), "values": window})
    if start + len(window) < len(values):
        report["more"] = (f"{len(values) - start - len(window)} more elements. Read them "
                          f"with start={start + len(window)} and a larger limit, or ask "
                          f"for unique=true.")
    return report


def _stats(values, size):
    """Min, max and mean of each component, so that a read of a large mesh
    needs no list of values to say what the attribute holds."""
    columns = [values] if size == 1 else list(zip(*values))
    stats = [{"min": min(column), "max": max(column),
              "mean": round(sum(column) / len(column), 6)} for column in columns]
    return stats[0] if size == 1 else stats


def get_skeleton(node_path, frame=None, pattern=None):
    """A KineFX skeleton: each joint with its name, its parent, and its place.

    A skeleton is points with a `name` attribute, wired by two-point
    primitives that go from a parent to a child. Nothing in the geometry says
    "joint", so this reads the shape and gives the answer that a caller wants.
    """
    node, geo = resolve(node_path, frame)
    named = geo.findPointAttrib("name")
    if not named:
        others = [index for index in range(len(node.outputNames()))
                  if index != OUTPUTS.get(node_path, 0) and _has_names(node, index)]
        hint = (f" Output {', '.join(map(str, others))} of this node holds a skeleton: give "
                f"output={others[0]}." if others else " Read it with mode 'summary'.")
        raise ValueError(f"{node_path} output {OUTPUTS.get(node_path, 0)} has no point "
                         f"attribute 'name', so it is not a skeleton.{hint}")
    names = list(geo.pointStringAttribValues("name"))
    parent_of = {}
    for prim in geo.prims():
        points = prim.points()
        if len(points) == 2:
            parent_of[points[1].number()] = points[0].number()
    has_transform = geo.findPointAttrib("transform")
    joints = []
    for point in geo.points():
        number = point.number()
        name = names[number] if number < len(names) else ""
        if not match.matches(pattern, name):
            continue
        parent = parent_of.get(number)
        joint = {"point": number, "name": name,
                 "parent": names[parent] if parent is not None and parent < len(names) else None,
                 "position": list(point.position())}
        if has_transform:
            joint["transform"] = list(point.attribValue("transform"))
        joints.append(joint)
    report = {"path": node_path, "count": len(joints), "total_joints": len(geo.points()),
              "roots": [joint["name"] for joint in joints if joint["parent"] is None],
              "joints": joints}
    if pattern and not joints:
        report["note"] = (f"The pattern {pattern!r} matched none of the {len(geo.points())} "
                          f"joints. Some names: {', '.join(names[:8])}.")
    return report


def _has_names(node, index):
    try:
        geometry = node.geometry(index)
    except hou.Error:
        return False
    return geometry is not None and geometry.findPointAttrib("name") is not None


def compare_nodes(node_path, against, match_attrib="name", attribs=None, frame=None,
                  worst=10):
    """What is different between the geometry of two nodes.

    The answer to "does my new node give the same result as the one it
    replaced". Points are matched by an attribute, not by their order, because
    two nodes that agree can still number their points in another way.
    """
    node, left = resolve(node_path, frame)
    other, right = resolve(against, frame)
    report = {"left": node_path, "right": against, "counts": {
        "left_points": len(left.points()), "right_points": len(right.points()),
        "left_prims": len(left.prims()), "right_prims": len(right.prims())}}

    left_names = _match_keys(left, match_attrib)
    right_names = _match_keys(right, match_attrib)
    shared = [key for key in left_names if key in right_names]
    report["matched"] = len(shared)
    report["only_left"] = [key for key in left_names if key not in right_names][:worst]
    report["only_right"] = [key for key in right_names if key not in left_names][:worst]

    wanted = attribs or sorted({attribute.name() for attribute in left.pointAttribs()}
                               & {attribute.name() for attribute in right.pointAttribs()})
    differences = {}
    for name in wanted:
        attribute = left.findPointAttrib(name)
        if attribute.dataType() == hou.attribData.String:
            continue
        gaps = []
        for key in shared:
            first = left.points()[left_names[key]].attribValue(name)
            second = right.points()[right_names[key]].attribValue(name)
            first = first if isinstance(first, (tuple, list)) else (first,)
            second = second if isinstance(second, (tuple, list)) else (second,)
            gap = max(abs(a - b) for a, b in zip(first, second))
            gaps.append((gap, key))
        if not gaps:
            continue
        gaps.sort(reverse=True)
        differences[name] = {"largest_difference": gaps[0][0],
                             "worst": [{"key": key, "difference": gap}
                                       for gap, key in gaps[:worst] if gap]}
    report["attributes"] = differences
    report["same"] = all(entry["largest_difference"] <= 1e-6
                         for entry in differences.values()) and not report["only_left"] \
        and not report["only_right"]
    return report


def _match_keys(geometry, match_attrib):
    """A map from the value of the matching attribute to the point number."""
    if geometry.findPointAttrib(match_attrib):
        values = list(geometry.pointStringAttribValues(match_attrib)) \
            if geometry.findPointAttrib(match_attrib).dataType() == hou.attribData.String \
            else list(geometry.pointFloatAttribValues(match_attrib))
        return {value: number for number, value in enumerate(values)}
    return {number: number for number in range(len(geometry.points()))}


def try_nodes(input_path, steps, frame=None, attrib_name=None, attrib_class="point",
              unique=False, start=0, count=10):
    """Run node types on the geometry of a node without touching the scene.

    Each step is {"node_type": "unpackusd", "parameters": {...}}. The steps run
    as verbs on a copy of the geometry, so the question "what would this node
    make here" costs no node, no undo and no change for the user. A type with
    no verb, such as an asset, runs as a temporary node in a hidden network.
    `attrib_name` reads that attribute on the result.
    """
    node, source = resolve(input_path, frame)
    category = hou.sopNodeTypeCategory()
    current = source
    ran = []
    for index, step in enumerate(steps):
        type_name = step["node_type"]
        node_type = hou.nodeType(category, type_name)
        if node_type is None:
            raise ValueError(f"Step {index}: there is no SOP type '{type_name}'.")
        verb = category.nodeVerb(type_name)
        parameters = dict(step.get("parameters") or {})
        # A verb has no node, so it cannot resolve a relative path. Make every
        # path absolute against the input node, or the verb reads nothing and
        # reports no error.
        for name, value in parameters.items():
            if isinstance(value, str) and value.startswith(".."):
                parameters[name] = node.node(value).path() if node.node(value) else value
        if verb:
            verb.setParms(_menu_indices(node_type, parameters, index))
            output = hou.Geometry()
            verb.execute(output, [current])
        else:
            output = _run_as_node(type_name, parameters, current, index)
        ran.append({"step": index, "node_type": type_name,
                    "points": len(output.points()), "prims": len(output.prims())})
        if not verb:
            ran[-1]["ran_as"] = "a temporary node: this type has no verb"
        if not len(output.points()) and not len(output.prims()):
            ran[-1]["note"] = ("This verb made no geometry. A relative path in a parameter "
                               "is the usual cause: a verb has no node to resolve it from.")
        current = output
    bbox = current.boundingBox()
    return {"input": input_path, "steps": ran, "result": {
        "num_points": len(current.points()), "num_prims": len(current.prims()),
        "point_attribs": [attribute_line(a) for a in current.pointAttribs()],
        "prim_attribs": [attribute_line(a) for a in current.primAttribs()],
        "detail_attribs": [attribute_line(a) for a in current.globalAttribs()],
        "bounding_box": {"min": list(bbox.minvec()), "max": list(bbox.maxvec())},
        "point_groups": [group.name() for group in current.pointGroups()],
        "prim_groups": [group.name() for group in current.primGroups()],
    }, **({"attrib": attrib_values(current, attrib_name, attrib_class, unique, start, count)}
          if attrib_name else {})}


def _menu_indices(node_type, parameters, step):
    """The parameters with each menu token as its index: a verb takes only
    the index, where parm_set and a node take the token."""
    group = node_type.parmTemplateGroup()
    found = dict(parameters)
    for name, value in parameters.items():
        template = group.find(name)
        if not isinstance(value, str) or template is None or                 template.type() == hou.parmTemplateType.String or                 not hasattr(template, "menuItems") or not template.menuItems():
            continue
        tokens, labels = list(template.menuItems()), list(template.menuLabels())
        if value in tokens:
            found[name] = tokens.index(value)
        elif value in labels:
            found[name] = labels.index(value)
        elif value.isdigit():
            found[name] = int(value)
        else:
            raise ValueError(f"Step {step}: '{value}' is not in the menu of {name}. "
                             f"Tokens: {', '.join(tokens)}.")
    return found


def _run_as_node(type_name, parameters, geometry, step):
    """One step as a real node in a hidden network that is deleted after, for
    a type with no verb. Undo does not record it."""
    with hou.undos.disabler():
        box = hou.node("/obj").createNode("geo", "__mcp_try")
        try:
            box.hide(True)
            stash = box.createNode("stash")
            stash.parm("stash").set(geometry)
            node = box.createNode(type_name)
            node.setInput(0, stash)
            node.setParms(parameters)
            try:
                node.cook(force=True)
            except hou.OperationFailed as error:
                raise ValueError(f"Step {step}: {type_name} did not cook: "
                                 f"{'; '.join(node.errors()) or error}") from error
            if node.errors():
                raise ValueError(f"Step {step}: {type_name} did not cook: "
                                 f"{'; '.join(node.errors())}")
            output = hou.Geometry()
            output.merge(node.geometry())
            return output
        finally:
            box.destroy()


def _no_attrib(geometry, name, attrib_class):
    finder = {"point": geometry.pointAttribs, "prim": geometry.primAttribs,
              "vertex": geometry.vertexAttribs, "detail": geometry.globalAttribs}[attrib_class]
    have = [attribute.name() for attribute in finder()]
    return (f"No {attrib_class} attribute '{name}'. This geometry has: "
            f"{', '.join(have) or 'none'}.")


def set_detail_attrib(node_path, attrib_name, value, frame=None):
    """Set a detail (global) attribute value."""
    node, geo = resolve(node_path, frame)
    geo.addAttrib(hou.attribType.Global, attrib_name, value)
    geo.setGlobalAttribValue(attrib_name, value)
    return {"path": node_path, "attrib": attrib_name, "value": value}


def get_groups(node_path, group_type="point", frame=None):
    """List geometry groups. group_type: point, prim, edge, vertex."""
    node, geo = resolve(node_path, frame)
    type_map = {
        "point": geo.pointGroups,
        "prim": geo.primGroups,
        "edge": geo.edgeGroups,
        "vertex": geo.vertexGroups,
    }
    fn = type_map.get(group_type)
    if not fn:
        raise ValueError(f"Unknown group type: {group_type}")
    groups = fn()
    return {
        "path": node_path,
        "type": group_type,
        "groups": [{"name": g.name(), "size": len(g)} for g in groups],
    }


def get_group_members(node_path, group_name, group_type="point", frame=None):
    """Get the members of a geometry group."""
    node, geo = resolve(node_path, frame)
    if group_type == "point":
        group = geo.findPointGroup(group_name)
    elif group_type == "prim":
        group = geo.findPrimGroup(group_name)
    else:
        raise ValueError(f"Unsupported group type for members: {group_type}")
    if not group:
        raise ValueError(f"Group not found: {group_name}")
    members = [elem.number() for elem in group.iterEntries()]
    return {"group": group_name, "type": group_type, "count": len(members), "members": members}


def get_bounding_box(node_path, frame=None):
    """Get the bounding box of a node's geometry."""
    node, geo = resolve(node_path, frame)
    bbox = geo.boundingBox()
    size = bbox.sizevec()
    center = bbox.center()
    return {
        "min": list(bbox.minvec()),
        "max": list(bbox.maxvec()),
        "size": list(size),
        "center": list(center),
    }


def get_prim_intrinsics(node_path, prim_index=0, frame=None):
    """Get intrinsic values of a primitive."""
    node, geo = resolve(node_path, frame)
    prims = geo.prims()
    if prim_index >= len(prims):
        raise ValueError(f"Prim index {prim_index} out of range (max {len(prims) - 1})")
    prim = prims[prim_index]
    intrinsics = {}
    for name in prim.intrinsicNames():
        intrinsics[name] = str(prim.intrinsicValue(name))
    return {"prim_index": prim_index, "intrinsics": intrinsics}


def find_nearest_point(node_path, position, frame=None):
    """Find the nearest point to a given position."""
    node, geo = resolve(node_path, frame)
    pos = hou.Vector3(position)
    pt = geo.nearestPoint(pos)
    return {
        "point_num": pt.number(),
        "position": list(pt.position()),
        "query_position": position,
    }


def geo_export(node_path, format="obj", output=None, frame=None):
    """Export geometry to a file. Formats: obj, gltf, glb, usd, usda, ply, bgeo.sc."""
    node, geo = resolve(node_path, frame)
    if not output:
        output = os.path.join(tempfile.gettempdir(), f"mcp_export.{format}")
    geo.saveToFile(output)
    bbox = geo.boundingBox()
    return {
        "exported": True,
        "file": output,
        "format": format,
        "num_points": len(geo.points()),
        "num_prims": len(geo.prims()),
        "num_vertices": geo.intrinsicValue("vertexcount"),
        "bounding_box": {
            "min": list(bbox.minvec()),
            "max": list(bbox.maxvec()),
        },
    }
