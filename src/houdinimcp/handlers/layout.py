"""Readable layout for a Houdini node network.

The built-in "Layout Selected Nodes" packs nodes by a spring model, which moves
work that was already arranged and makes long diagonal wires. This module puts
the nodes on a grid instead: one row per dependency depth, and a column order
that is chosen to keep wires short and to keep crossings low.

Use:

    layout(hou.node("/obj/geo1"))              # the whole network
    layout(nodes=[...])                        # only these nodes
    layout(nodes=..., origin=(5.0, 0.0))       # place them somewhere
    place([new_node, ...])                     # new nodes, in place
    problems(hou.node("/obj/geo1"))            # list layout faults

Rules that `place` follows (the way an artist lays out a SOP network by hand):

1. A node sits below every one of its inputs. A child is never higher.
2. The first input sets the column: a chain reads straight down the page.
3. A new node on a wire takes the slot under its input. The nodes below it
   move down one row, and they keep their layout.
4. A second branch from the same node goes in the next free column to the
   right, not on top of the first branch.
5. A side branch that merges back ends one row above the node it feeds.
6. A node with no input sits one row above, one column right of its reader.
7. No two nodes share a slot (a slot is wide enough for the node name).
8. New nodes go next to what they connect to, never in a far free area.

`layout(nodes=...)` on a part of a network that already has other nodes uses
`place`. The nodes that are not in the set only move down, and only to keep
rule 1.
"""

import hou

COLUMN_STEP = 3.6   # horizontal distance between two nodes in the same row;
                    # wide enough that a node name does not cover its neighbour
ROW_STEP = 1.1      # vertical distance between two rows
SWEEPS = 6          # ordering passes; more is slower and rarely better


def _depths(nodes):
    """Row of each node: one more than the deepest input inside the set."""
    inside = set(nodes)
    depth = {}

    def walk(node, seen):
        if node in depth:
            return depth[node]
        if node in seen:          # a feedback loop, for example a solver SOP
            return 0
        seen.add(node)
        best = 0
        for parent in node.inputs():
            if parent in inside:
                best = max(best, walk(parent, seen) + 1)
        seen.discard(node)
        depth[node] = best
        return best

    for node in nodes:
        walk(node, set())

    # A node with no input inside the set would sit on the top row even when it
    # feeds something far down, which draws a long wire across the whole graph.
    # Drop it to just above the first node that reads it.
    for node in nodes:
        if any(parent in inside for parent in node.inputs()):
            continue
        readers = [d for d in node.outputs() if d in inside]
        if readers:
            depth[node] = min(depth[d] for d in readers) - 1

    lowest = min(depth.values())
    if lowest < 0:
        for node in depth:
            depth[node] -= lowest
    return depth


def _order(rows, nodes):
    """Choose the column order of every row, so that wires stay short.

    Each node is pulled to the average column of the nodes it connects to in the
    row above, then in the row below. A few passes are enough: the graphs here
    are small and the result stops changing.
    """
    inside = set(nodes)
    column = {}
    for row in sorted(rows):
        for i, node in enumerate(rows[row]):
            column[node] = float(i)

    def barycentre(node, neighbours):
        values = [column[n] for n in neighbours if n in inside and n in column]
        return sum(values) / len(values) if values else None

    for sweep in range(SWEEPS):
        downward = sweep % 2 == 0
        for row in (sorted(rows) if downward else sorted(rows, reverse=True)):
            keys = {}
            for node in rows[row]:
                if downward:
                    neighbours = [n for n in node.inputs() if n]
                else:
                    neighbours = [c for o in node.outputs() for c in [o]]
                keys[node] = barycentre(node, neighbours)
            # A node with no neighbour in that direction keeps where it is.
            fallback = {node: column[node] for node in rows[row]}
            rows[row].sort(key=lambda n: keys[n] if keys[n] is not None else fallback[n])
            for i, node in enumerate(rows[row]):
                column[node] = float(i)
    return column


def layout(parent=None, nodes=None, origin=None):
    """Place nodes on a grid. Returns the bounding box that was used."""
    if nodes is None:
        if parent is None:
            raise ValueError("Give parent, a network, or nodes, a list of nodes.")
        nodes = [n for n in parent.children() if isinstance(n, hou.Node)]
    nodes = [n for n in nodes if n is not None]
    if not nodes:
        return None
    parent = parent or nodes[0].parent()
    if origin is None:
        if any(n not in set(nodes) for n in parent.children()):
            # A part of a network goes next to the nodes it connects to.
            return place(nodes)
        origin = (0.0, 0.0)

    depth = _depths(nodes)
    rows = {}
    for node in nodes:
        rows.setdefault(depth[node], []).append(node)
    for row in rows:
        rows[row].sort(key=lambda n: n.name())
    column = _order(rows, nodes)

    width = max(len(rows[row]) for row in rows)

    for row in sorted(rows):
        members = rows[row]
        # Centre each row on the widest one, so the trunk of the graph is straight.
        offset = (width - len(members)) * 0.5
        for node in members:
            x = origin[0] + (column[node] + offset) * COLUMN_STEP
            y = origin[1] - row * ROW_STEP
            node.setPosition(hou.Vector2(x, y))

    return (origin[0], origin[1] - max(rows) * ROW_STEP,
            origin[0] + width * COLUMN_STEP, origin[1])


SLOT_X = COLUMN_STEP * 0.9   # two nodes closer than this in x and y share a slot
SLOT_Y = ROW_STEP * 0.9


def _pos(node):
    return node.position()


def _downstream(node):
    """Every node that reads node, directly or through other nodes."""
    found, todo = set(), [node]
    while todo:
        for reader in todo.pop().outputs():
            if reader not in found:
                found.add(reader)
                todo.append(reader)
    return found


def _component(node):
    """Every node joined to node by wires, in either direction."""
    found, todo = {node}, [node]
    while todo:
        current = todo.pop()
        for other in list(current.inputs()) + list(current.outputs()):
            if other is not None and other not in found:
                found.add(other)
                todo.append(other)
    return found


def _occupied(x, y, others):
    return any(abs(_pos(n)[0] - x) < SLOT_X and abs(_pos(n)[1] - y) < SLOT_Y
               for n in others)


def _free_x(x, y, others):
    """First free slot at x or in the columns to its right (rule 7)."""
    while _occupied(x, y, others):
        x += COLUMN_STEP
    return x


def _push_down(reader, below_y, skip):
    """Move reader, and the nodes of its graph at or under its row, down so
    that reader sits at below_y (rules 1 and 3). They keep their layout."""
    delta = _pos(reader)[1] - below_y
    if delta <= 1e-4:
        return
    top = _pos(reader)[1] + 1e-4
    for node in _component(reader):
        if node not in skip and _pos(node)[1] <= top:
            node.setPosition(_pos(node) - hou.Vector2(0.0, delta))


def place(nodes):
    """Place new nodes next to the nodes they connect to. Other nodes only move
    down, to make room. Returns the nodes that were placed."""
    nodes = [n for n in nodes if n is not None]
    if not nodes:
        return []
    network = nodes[0].parent()
    pending = set(nodes)
    depth = _depths(nodes)

    def is_source(node):
        return not any(i is not None for i in node.inputs())

    def heads_new_chain(node):
        # A source whose readers have no other input starts a new chain.
        return all(all(i == node or i is None for i in r.inputs())
                   for r in node.outputs() if r in pending)

    first = [n for n in nodes if not (is_source(n) and not heads_new_chain(n))]
    later = [n for n in nodes if n not in first]
    order = sorted(first, key=lambda n: depth[n]) + later

    for node in order:
        pending.discard(node)
        others = [n for n in network.children() if n != node and n not in pending]
        parents = [i for i in node.inputs() if i is not None and i not in pending]
        readers = [r for r in node.outputs() if r not in pending]

        if parents:
            # Rules 1 and 2: under the lowest input, in the first input's column.
            x = _pos(parents[0])[0]
            y = min(_pos(p)[1] for p in parents) - ROW_STEP
            # Rule 3: the node's own readers make room, so they do not block.
            downstream = _downstream(node)
            x = _free_x(x, y, [n for n in others if n not in downstream])
        elif readers:
            # Rule 6: one row above, one column right of the first reader.
            reader = min(readers, key=lambda r: _pos(r)[1])
            x = _pos(reader)[0] + COLUMN_STEP
            y = _pos(reader)[1] + ROW_STEP
            x = _free_x(x, y, others)
        else:
            # Rule 8: nothing to connect to; under the lowest node, same column.
            if others:
                lowest = min(others, key=lambda n: _pos(n)[1])
                x, y = _pos(lowest)[0], _pos(lowest)[1] - ROW_STEP
            else:
                x, y = 0.0, 0.0
            x = _free_x(x, y, others)
        node.setPosition(hou.Vector2(x, y))

        for reader in readers:
            _push_down(reader, y - ROW_STEP, skip=set(nodes) - {reader})

    _align_side_branches(nodes)
    return nodes


def _align_side_branches(nodes):
    """Rule 5: move a new side chain down so it ends one row above the node it
    feeds, when the slots on the way are free."""
    new = set(nodes)
    for last in nodes:
        readers = last.outputs()
        if len(readers) != 1:
            continue
        reader = readers[0]
        if abs(_pos(reader)[0] - _pos(last)[0]) < SLOT_X:
            continue                                   # same column: the trunk
        chain = [last]
        while True:
            parents = [i for i in chain[-1].inputs() if i is not None]
            if (len(parents) == 1 and parents[0] in new
                    and len(parents[0].outputs()) == 1):
                chain.append(parents[0])
            else:
                break
        delta = _pos(last)[1] - (_pos(reader)[1] + ROW_STEP)
        if delta <= 1e-4:
            continue
        others = [n for n in last.parent().children() if n not in chain]
        moved = [(_pos(n)[0], _pos(n)[1] - delta) for n in chain]
        if any(_occupied(x, y, others) for x, y in moved):
            continue
        for node, (x, y) in zip(chain, moved):
            node.setPosition(hou.Vector2(x, y))


def problems(network, nodes=None):
    """Layout faults in a network: children above an input, shared slots.
    With `nodes`, only the faults that involve one of them."""
    faults = []
    children = network.children()
    mine = set(nodes) if nodes else set(children)
    for node in children:
        for parent in node.inputs():
            if parent is not None and (node in mine or parent in mine) \
                    and _pos(node)[1] > _pos(parent)[1] - SLOT_Y:
                faults.append("%s is not below its input %s" % (node.name(), parent.name()))
    for i, a in enumerate(children):
        for b in children[i + 1:]:
            if (a in mine or b in mine) and _occupied(_pos(a)[0], _pos(a)[1], [b]):
                faults.append("%s and %s share a slot" % (a.name(), b.name()))
    return faults
