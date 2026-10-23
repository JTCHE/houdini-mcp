"""Split a SOP network into stage subnets, Houdini style: each stage reads the
results of the others through an IN_ Object Merge from an OUT_ Null, so each
result has one source of truth."""
import posixpath
import re

import hou

from . import layout

# A relative node path in a parameter or in code: ../name, ../../a/b, ./name.
RELATIVE = re.compile(r"(?<![\w.$/])((?:\.\./)+|\./)([A-Za-z_][\w.-]*(?:/[\w.-]+)*)")


def _record_wires(network):
    wires = []
    for reader in network.children():
        for wire in reader.inputConnections():
            item, output = wire.inputItem(), wire.outputIndex()
            while isinstance(item, hou.NetworkDot):
                connection = item.inputConnections()
                if not connection:
                    item = None
                    break
                output = connection[0].outputIndex()
                item = connection[0].inputItem()
            if item is not None:
                wires.append((item.name(), output, reader.name(), wire.inputIndex()))
    return wires


def _references(network):
    """Each node path in a string parameter or an expression of the nodes of
    `network`, before the move: (node name, parm name, raw text)."""
    found = []
    for node in network.children():
        for parm in node.parms():
            try:
                raw = parm.expression()
            except hou.OperationFailed:
                template = parm.parmTemplate()
                if template.type() != hou.parmTemplateType.String:
                    continue
                raw = parm.unexpandedString()
            if "/" in raw:
                found.append((node.name(), parm.name(), raw))
    return found


def _rewrite(text, old_node, new_node, where):
    """`text` with each node path that pointed at a node of the network made
    right for the new place of the node that holds it. `where(name)` is the
    new absolute path of a node of the network."""
    network = posixpath.dirname(old_node)
    unresolved = []

    def fix(path, absolute):
        target = path if absolute else posixpath.normpath(posixpath.join(old_node, path))
        if not target.startswith(network + "/"):
            return None
        name, _, rest = target[len(network) + 1:].partition("/")
        moved = where(name)
        if moved is None:
            if hou.node(posixpath.join(network, name)) is None:
                unresolved.append(path)
            return None
        new = moved + ("/" + rest if rest else "")
        return new if absolute else posixpath.relpath(new, new_node)

    def relative(match):
        better = fix(match.group(0), False)
        return better if better is not None else match.group(0)

    text = RELATIVE.sub(relative, text)
    absolute = re.compile(re.escape(network) + r"/[\w.-]+(?:/[\w.-]+)*")
    text = absolute.sub(lambda match: fix(match.group(0), True) or match.group(0), text)
    return text, unresolved


def split(network_path, stages):
    """Move the nodes named in `stages` ({stage name: [node names]}) into one
    subnet for each stage, and wire every result that crosses a stage through
    an OUT_ Null and an IN_ Object Merge. Node paths in parameters and in code
    are rewritten for the new places."""
    network = hou.node(network_path)
    if network is None:
        raise ValueError(f"Node not found: {network_path}")
    if network.childTypeCategory() != hou.sopNodeTypeCategory():
        raise ValueError(f"{network_path} is not a SOP network. split works on SOPs, "
                         f"where an Object Merge can read another stage.")
    stage_of = {}
    for stage, names in stages.items():
        for name in names:
            if network.node(name) is None:
                raise ValueError(f"Stage {stage}: no node '{name}' in {network_path}.")
            if name in stage_of:
                raise ValueError(f"'{name}' is in two stages: {stage_of[name]} and {stage}.")
            stage_of[name] = stage
    for stage in stages:
        if network.node(stage) is not None:
            raise ValueError(f"{network_path} has a node '{stage}' already. Give the stage "
                             f"another name.")

    wires = _record_wires(network)
    old_paths = {node.name(): node.path() for node in network.children()}
    references = _references(network)
    display = next((node.name() for node in network.children()
                    if node.isDisplayFlagSet()), None)

    def where(name):
        if name in stage_of:
            return f"{network.path()}/{stage_of[name]}/{name}"
        return f"{network.path()}/{name}" if name in old_paths else None

    report = {"subnets": [], "out_nulls": [], "object_merges": [], "rewritten": [],
              "unresolved": []}
    subnets = {}
    for stage, names in stages.items():
        items = [network.node(name) for name in names]
        center = sum((node.position() for node in items), hou.Vector2()) / len(items)
        subnet = network.createNode("subnet", stage)
        subnet.setPosition(center)
        hou.moveNodesTo(items, subnet)
        subnets[stage] = subnet
        report["subnets"].append(subnet.path())

    def node_at(name):
        stage = stage_of.get(name)
        return (subnets[stage] if stage else network).node(name)

    outs, merges = {}, {}
    for source, output, reader, index in wires:
        here, there = stage_of.get(source), stage_of.get(reader)
        if here == there:
            continue
        feed = node_at(source)
        if here is not None:
            key = (source, output)
            if key not in outs:
                name = f"OUT_{source}" + (f"_{output}" if output else "")
                out = subnets[here].createNode("null", name)
                out.setInput(0, feed, output)
                out.setPosition(feed.position() - hou.Vector2(0, layout.ROW_STEP))
                outs[key] = out
                report["out_nulls"].append(out.path())
            feed, output = outs[key], 0
        home = subnets[there] if there else network
        key = (feed.path(), output, home.path())
        if key not in merges:
            merge = home.createNode("object_merge", f"IN_{source}" + (
                f"_{key[1]}" if here is None and key[1] else ""))
            merge.parm("objpath1").set(posixpath.relpath(feed.path(), merge.path()))
            merges[key] = merge
            report["object_merges"].append(
                {"path": merge.path(), "reads": merge.parm("objpath1").eval()})
        node_at(reader).setInput(index, merges[key])
        if there is None:
            merges[key].setPosition(node_at(reader).position() + hou.Vector2(0, layout.ROW_STEP))

    for name, parm, raw in references:
        holder = node_at(name)
        if holder is None:
            continue
        new, unresolved = _rewrite(raw, old_paths[name], holder.path(), where)
        report["unresolved"] += [{"node": holder.path(), "parm": parm, "path": path}
                                 for path in unresolved]
        if new == raw:
            continue
        target = holder.parm(parm)
        try:
            target.expression()
            target.setExpression(new)
        except hou.OperationFailed:
            target.set(new)
        report["rewritten"].append({"node": holder.path(), "parm": parm,
                                    "old": raw[:200], "new": new[:200]})

    for dot in network.networkDots():
        if not dot.outputConnections():
            dot.destroy()
    for stage, subnet in subnets.items():
        layout.layout(subnet)
    if display in stage_of:
        subnets[stage_of[display]].setDisplayFlag(True)
        subnets[stage_of[display]].setRenderFlag(True)
    return report
