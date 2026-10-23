"""Node CRUD, wiring, flags, layout, and material handlers."""
import difflib
import re

import hou

from . import layout, match
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
        close = close_types(parent, node_type)
        hint = (f"Did you mean: {', '.join(close)}?" if close else
                "Read the type names with scene_overview mode 'node_types'.")
        raise ValueError(f"Houdini has no node type '{node_type}' in {parent_path}. "
                         f"{hint}") from error

    report = {"path": node.path(), "type": node.type().name()}
    rule = house_rule(node)
    if rule:
        report["house_rule"] = rule
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
        report.update(place_node(node))
    if parameters:
        # The same write path as parm_set, so a write that does nothing is
        # reported here too instead of passing for success.
        written = parameters_handler.set_parameters(node.path(), parameters)
        # A clean write needs no report: the caller sent the value. Only a
        # write that failed or that carries a warning comes back.
        notable = [change for change in written["changes"]
                   if not change["applied"] or change.get("warnings") or change.get("reason")]
        report["parameters_set"] = len(written["changes"]) - len(written["not_applied"])
        if notable:
            report["parameters"] = notable
        if written["not_applied"]:
            report["not_applied"] = written["not_applied"]
    return report


def house_rule(node):
    """The convention of the user that a new node breaks, or None."""
    kind = node.type().name()
    if kind in ("attribexpression", "groupexpression"):
        return ("An Expression SOP hides its logic behind a preset menu and fields. Use an "
                "Attribute Wrangle with the same one line instead, for example "
                "`@P = lerp(v@center, @P, 1.4);` or `i@group_name = condition;`.")
    if kind == "output":
        others = [other.path() for other in node.parent().children()
                  if other != node and other.type().name() == "output"]
        if others:
            return (f"This network already has an Output SOP ({', '.join(others)}). Keep one "
                    f"Output, the last node, named OUT_<NAME>: merge the results into it. "
                    f"A result that another network reads is a Null named OUT_<NAME>.")
    return None


def close_types(parent, node_type, count=5):
    """The node types under `parent` whose names are close to `node_type`.

    A name compares without its namespace and version, so "mountian" finds
    "mountain::2.0" as well as "mountain".
    """
    names = parent.childTypeCategory().nodeTypes()
    bare = {}
    for full in names:
        bare.setdefault(hou.hda.componentsFromFullNodeTypeName(full)[2], []).append(full)
    found = difflib.get_close_matches(node_type, list(bare), n=count, cutoff=0.7)
    return [full for name in found for full in bare[name]][:count]


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


def delete_nodes(paths, force=False):
    """Delete nodes, dots, sticky notes or network boxes.

    A node that feeds a node outside `paths` is refused unless `force`: a
    script that took a node behind a dot for "the input" deletes a node that
    the graph still reads, and the cook goes empty with no error.
    """
    items = []
    for path in paths:
        item = hou.node(path) or hou.item(path)
        if not item:
            raise ValueError(f"Node not found: {path}")
        items.append(item)
    going = {item.path() for item in items}
    if not force:
        kept = {}
        for item in items:
            if not isinstance(item, hou.Node):
                continue
            # outputs() follows dots; outputConnections() stops at a dot.
            readers = sorted({reader.path() for reader in item.outputs()} - going)
            if readers:
                kept[item.path()] = readers
        if kept:
            raise ValueError(
                f"Nothing deleted. These nodes still feed nodes that stay: {kept}. Rewire "
                f"the readers first, add them to paths, or give force=true.")
    deleted = []
    for item in items:
        deleted.append(item.path())
        item.destroy()
    return {"deleted": deleted}


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

    for connection in node.inputConnections():
        in_node = connection.inputNode()
        entry = {"index": connection.inputIndex()}
        item = connection.inputItem()
        if item is not None and item != in_node:
            # A dot (or a subnet input) is what is wired here; the node is behind it.
            entry["via"] = item.path() if hasattr(item, "path") else str(item)
        if in_node is not None:
            entry.update(name=in_node.name(), path=in_node.path(), type=in_node.type().name())
        node_info["inputs"].append(entry)

    for out_conn in node.outputConnections():
        out_node = out_conn.outputNode()
        if out_node is None:
            # The wire goes into a dot; list the readers behind it.
            node_info.setdefault("outputs_via_dots", []).extend(
                reader.path() for reader in out_conn.outputItem().outputs())
            continue
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


def layout_problems(path):
    """The layout faults of a network: a node above its input, and two nodes
    in one slot, where one name covers the other. A position alone does not
    show that; this is what a picture of the network editor would show."""
    network = hou.node(path)
    if not network:
        raise ValueError(f"Node not found: {path}")
    faults = layout.problems(network)
    return {"path": path, "nodes": len(network.children()), "count": len(faults),
            "problems": faults}


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
        items = [_item(path) for path in paths]
        node = items[0].parent()
        result = layout.layout(nodes=items)
        report = {"path": node.path(), "laid_out": len(items)}
        faults = layout.problems(node, items)
    else:
        result = layout.layout(node)
        report = {"path": node.path(), "laid_out": "every node in this network",
                  "warning": "Every node moved, and that includes the nodes that the user "
                             "placed by hand. Give `paths` to move only your own nodes."}
        faults = layout.problems(node)
    report.update(_moves(result["moved"]))
    report["dots"] = result.get("dots")
    if faults:
        report["layout_problems"] = faults
    return report


def _item(path):
    item = hou.node(path) or hou.item(path)
    if item is None:
        raise ValueError(f"Node not found: {path}")
    return item


def _moves(moved, limit=40):
    """{path: [old, new]} as a short report: every move, up to `limit`."""
    rounded = {path: [[round(v, 2) for v in old], [round(v, 2) for v in new]]
               for path, (old, new) in moved.items()}
    if len(rounded) <= limit:
        return {"moved": rounded} if rounded else {}
    return {"moved_count": len(rounded), "moved": dict(list(rounded.items())[:limit])}


MADE = "houdinimcp_made"


def place_node(node):
    """Put a new node where an artist would: under its input, in a free slot.

    Houdini's own layout moves every node in the network. A new node that
    places itself removes the reason to call that. Only the readers of the
    node move, and only down, to make room; a node they then cover moves down
    too. The node is marked as made by an agent, so a later wire can place it
    again without a move of a node that the user placed. Returns the moves of
    the other nodes and the layout faults that involve the node.
    """
    node.setUserData(MADE, "1")
    moved = layout.place([node])
    moved.pop(node.path(), None)
    report = _moves(moved)
    faults = layout.problems(node.parent(), [node])
    if faults:
        report["layout_problems"] = faults
    return report


def insert_node(source_path, node_type=None, path=None, reader_path=None, name=None,
                parameters=None, output=0):
    """Put a node on the wires out of `source_path`: a new one of `node_type`,
    or the node at `path`. With `reader_path`, only the wires into that node
    (every input that reads the source, for example the three streams of a
    Vellum chain); else every reader of that output."""
    source = hou.node(source_path)
    if not source:
        raise ValueError(f"Node not found: {source_path}")
    reader = hou.node(reader_path) if reader_path else None
    if reader_path and reader is None:
        raise ValueError(f"Node not found: {reader_path}")
    if path:
        node = hou.node(path)
        if node is None:
            raise ValueError(f"Node not found: {path}")
    else:
        if not node_type:
            raise ValueError("insert needs node_type for a new node, or path for one that "
                             "exists.")
        made = create_node(node_type, source.parent().path(), name, position=[0, 0])
        node = hou.node(made["path"])
    node.setUserData(MADE, "1")
    result = layout.insert(node, source, reader, output)
    result["moved"].pop(node.path(), None)
    report = {"path": node.path(), "source": source.path(), "rewired": result["rewired"]}
    report.update(_moves(result["moved"]))
    if parameters:
        from . import parameters as parameters_handler
        written = parameters_handler.set_parameters(node.path(), parameters)
        report["parameters"] = written
    faults = layout.problems(node.parent(), [node, source] + [hou.node(r["reader"])
                                                              for r in result["rewired"]])
    if faults:
        report["layout_problems"] = faults
    return report


def place_chain(paths, reader_path, input_index=0):
    """Wire the nodes at `paths` in order into input `input_index` of
    `reader_path`, and place them as a side chain."""
    chain = [_item(path) for path in paths]
    reader = hou.node(reader_path)
    if reader is None:
        raise ValueError(f"Node not found: {reader_path}")
    for node in chain:
        node.setUserData(MADE, "1")
    result = layout.place_chain(chain, reader, input_index)
    report = {"chain": [node.path() for node in chain], "reader": reader.path(),
              "input": input_index, "dots": result["dots"]}
    report.update(_moves(result["moved"]))
    faults = layout.problems(reader.parent(), chain + [reader])
    if faults:
        report["layout_problems"] = faults
    return report


def create_note(parent_path, text, name=None, position=None, color=None):
    """A sticky note: the text that tells a person what a part of a network does."""
    parent = _network(parent_path)
    note = parent.createStickyNote(name)
    note.setText(text)
    # A note sized to its text, about 0.1 network units for each character.
    lines = text.splitlines() or [""]
    width = max(2.0, 0.1 * max(map(len, lines)))
    note.setSize(hou.Vector2(width, max(1.0, 0.25 * len(lines) + 0.5)))
    if position:
        note.setPosition(hou.Vector2(position[0], position[1]))
    else:
        children = parent.children()
        if children:
            right = max(child.position()[0] + child.size()[0] for child in children)
            top = max(child.position()[1] for child in children)
            note.setPosition(hou.Vector2(right + 1, top))
    if color:
        note.setColor(hou.Color(*color))
    return {"path": note.path(), "type": "sticky note"}


def create_box(parent_path, paths, text=None, name=None, color=None):
    """A network box around `paths`, with `text` as its comment."""
    if text and (len(text) > 24 or len(text.split()) > 3):
        raise ValueError(f"A network box comment is a title of one to three words, such as "
                         f"'SIM MESH'. {text!r} is longer. Give the box a short title, and "
                         f"put the explanation in a sticky note with mode 'note'.")
    parent = _network(parent_path)
    items = [hou.node(path) or hou.item(path) for path in paths]
    for path, item in zip(paths, items):
        if item is None:
            raise ValueError(f"Not found: {path}")
        # A box in a box draws behind its parent, and their nodes overlap.
        if item.parentNetworkBox() is not None or isinstance(item, hou.NetworkBox):
            raise ValueError(f"{path} is already in the network box "
                             f"{(item.parentNetworkBox() or item).name()}. Never put a box "
                             f"inside a box: put these nodes in one box, or take them out "
                             f"of the other box first.")
    box = parent.createNetworkBox(name)
    for item in items:
        box.addItem(item)
    if text:
        box.setComment(text)
    box.fitAroundContents()
    if color:
        box.setColor(hou.Color(*color))
    return {"path": box.path(), "type": "network box", "holds": len(paths)}


def _network(path):
    parent = hou.node(path)
    if not parent:
        raise ValueError(f"Network not found: {path}")
    return parent


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


COPY_OF = "houdinimcp_copy_of"


def copy_nodes(paths, destination_path=None, suffix=None, names=None):
    """Copy a set of nodes, and say which copy came from which node.

    `hou.copyNodesTo` returns the copies in an order of its own, so a loop
    that pairs the sources with the copies by position names them wrong. Each
    source carries its path in its user data during the copy, and the copy
    that carries the same data is its copy. The wires inside the set stay; a
    wire from a node outside the set goes to the same node. Copies in the same
    network go to the right of the sources.
    """
    sources = []
    for path in paths:
        node = hou.node(path)
        if not node:
            raise ValueError(f"Node not found: {path}")
        sources.append(node)
    network = hou.node(destination_path) if destination_path else sources[0].parent()
    if network is None:
        raise ValueError(f"Destination not found: {destination_path}")
    for node in sources:
        node.setUserData(COPY_OF, node.path())
    try:
        copies = {copy.userData(COPY_OF): copy for copy in hou.copyNodesTo(sources, network)}
    finally:
        for node in sources:
            node.destroyUserData(COPY_OF, must_exist=False)
    for copy in copies.values():
        copy.destroyUserData(COPY_OF, must_exist=False)
        copy.setUserData(MADE, "1")

    inside = {node.path() for node in sources}
    unwired, renamed = [], []
    for node in sources:
        copy = copies[node.path()]
        # A wire from outside the set: the copy reads the same node.
        for wire in node.inputConnections():
            source, index = wire.inputNode(), wire.inputIndex()
            if source is None or source.path() in inside or copy.input(index) is not None:
                continue
            if source.parent() == network:
                copy.setInput(index, source, wire.outputIndex())
            else:
                unwired.append({"copy": copy, "input": index, "was": source.path()})
        wanted = (names or {}).get(node.path()) or (names or {}).get(node.name()) \
            or (node.name() + suffix if suffix else None)
        if wanted:
            copy.setName(wanted, unique_name=True)
            if copy.name() != wanted:
                renamed.append({"asked": wanted, "got": copy.name()})

    if network == sources[0].parent():
        xs = [node.position()[0] for node in sources]
        shift = hou.Vector2(max(xs) - min(xs) + layout.COLUMN_STEP, 0.0)
        for node in sources:
            copies[node.path()].setPosition(node.position() + shift)
    report = {"copies": {path: copy.path() for path, copy in copies.items()},
              "network": network.path()}
    if renamed:
        report["renamed_by_houdini"] = renamed
    if unwired:
        # The path after the rename, so it is the path that exists.
        report["not_wired"] = [{**entry, "copy": entry["copy"].path()} for entry in unwired]
        report["note"] = ("These inputs came from nodes in another network, so the copies "
                          "have no input there. Wire them with connect.")
    faults = layout.problems(network, list(copies.values()))
    if faults:
        report["layout_problems"] = faults
    return report


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


TYPE_LIMIT = 300


def list_node_types(category=None, pattern=None):
    """The node types of one category whose name or label match `pattern`.

    A category such as Sop holds thousands of types, and a client refuses an
    answer that holds all of them. Past TYPE_LIMIT the list is cut, and the
    answer says by how much.
    """
    categories = hou.nodeTypeCategories()
    if category and category not in categories:
        same = [name for name in categories if name.lower() == category.lower()]
        if not same:
            raise ValueError(f"No category '{category}'. Categories: "
                             f"{', '.join(sorted(categories))}.")
        category = same[0]
    result = []
    for cat_name, cat in categories.items():
        if category and cat_name != category:
            continue
        for name, nt in cat.nodeTypes().items():
            if match.matches(pattern, name, nt.description()):
                result.append({"name": name, "category": cat_name,
                               "label": nt.description()})
    report = {"count": len(result), "types": result[:TYPE_LIMIT]}
    if len(result) > TYPE_LIMIT:
        report["cut"] = (f"Only the first {TYPE_LIMIT} of {len(result)} types. Give "
                         f"category and pattern, for example pattern='*retarget*|*ik*'.")
    return report


def connect_nodes_batch(connections):
    """Connect multiple node pairs at once.

    connections: list of dicts with src_path, dst_path, dst_input_index, src_output_index
    """
    results = []
    for conn in connections:
        # Either end can be a network dot.
        src = hou.node(conn["src_path"]) or hou.item(conn["src_path"])
        dst = hou.node(conn["dst_path"]) or hou.item(conn["dst_path"])
        if not src:
            raise ValueError(f"Source not found: {conn['src_path']}")
        if not dst:
            raise ValueError(f"Destination not found: {conn['dst_path']}")
        if isinstance(dst, hou.NetworkDot):
            dst.setInput(src, conn.get("src_output_index", 0))
        else:
            dst.setInput(conn.get("dst_input_index", 0), src, conn.get("src_output_index", 0))
        results.append({
            "src": src.path(), "dst": dst.path(),
            "dst_input": conn.get("dst_input_index", 0),
        })
    report = {"connected": len(results), "connections": results}
    # A node that an agent made was placed before it had this wire, at either
    # end of it. Place it again; a node that the user placed only moves down to
    # make room, as when a new node goes in on a wire.
    made = {node.path(): node for node in (hou.node(result[end]) for result in results
                                           for end in ("src", "dst"))
            if isinstance(node, hou.Node) and node.userData(MADE)}
    if made:
        moved = layout.place(list(made.values()))
        network = next(iter(made.values())).parent()
        report["placed_again"] = list(made)
        others = {path: move for path, move in moved.items() if path not in made}
        report.update({"moved_" + key: value for key, value in _moves(others).items()})
        faults = layout.problems(network, list(made.values()))
        if faults:
            report["layout_problems"] = faults
    return report


def reorder_inputs(path, input_indices):
    """Reorder the inputs of a node by specifying the new index order."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    # The wired items, not inputs(): a dot on a wire must stay on it.
    current_inputs = [None] * len(node.inputs())
    for connection in node.inputConnections():
        current_inputs[connection.inputIndex()] = connection.inputItem()
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
