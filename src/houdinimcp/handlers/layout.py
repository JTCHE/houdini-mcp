"""Readable layout for a Houdini node network: the code of the user's Smart
Layout shelf tool. The shelf tool imports this module, so the MCP and the
shelf tool lay out a network the same way.

The built-in "Layout Selected Nodes" packs nodes by a spring model, which moves
work that was already arranged and makes long diagonal wires. This module puts
the nodes on a grid instead: one row per dependency depth, and each node in
the column of its first input.

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

`layout` moves only the nodes it is given. Its top-left corner stays. The
first input of a node is always straight above it; other inputs go to the
right. `place` is for new nodes: there, other nodes move down to make room.

    layout(network)                 # every node
    layout(nodes=[...])             # only these nodes; the others stay
    run()                           # shelf tool: the selection
    place([new_node, ...])          # new nodes next to what they connect to
    insert(node, source, reader)    # a new node on the wires between two nodes
    place_chain([a, b, c], reader, input_index)
    problems(network)               # layout faults and house rules
"""
import math

import hou

COLUMN_STEP = 3.6   # horizontal distance between two nodes in the same row;
                    # wide enough that a node name does not cover its neighbour
ROW_STEP = 1.1      # vertical distance between two rows
CHAR = 0.1           # width of one character of drawn text
LINE = 0.25          # height of one line of drawn text
# Wire shapes, measured on screen grabs: the stub of a straight wire, and the
# corner radius of a rounded wire.
STUB = 0.12
# The node type label that the editor draws above the name.
TYPE_LABEL = 0.2
CORNER = 0.25
# The editor draws at most this many characters of a comment or path line.
TRUNCATE = 40
# The parameter whose value a node type draws under its name.
DESCRIPTIVE = {"object_merge": "objpath1", "file": "file", "filecache": "file",
               "alembic": "fileName", "filemerge": "file", "rop_geometry": "sopoutput",
               "usdimport": "filepath1", "sopimport": "soppath", "fetch": "source",
               "objectmerge": "objpath1"}
# Node types whose job is the end of a chain: they feed nothing on purpose.
TERMINAL = ("output", "null", "rop_", "filecache", "usdrender", "karma", "opengl",
            "ifd", "geometry", "alembic_rop", "fbx", "subnet", "matnet", "ropnet")


# ---------------------------------------------------------------------------
# What the editor draws.

def _pos(item):
    return item.position()


def _size(item):
    if isinstance(item, hou.NetworkDot):
        return hou.Vector2(0.1, 0.1)
    return item.size()


def _text_lines(node):
    """The lines that the editor draws right of a node: name, comment, path."""
    if isinstance(node, hou.NetworkDot):
        return []
    lines = [node.name()]
    try:
        if node.isGenericFlagSet(hou.nodeFlag.DisplayComment) and node.comment():
            lines += node.comment().splitlines()
    except (hou.Error, AttributeError):
        pass
    name = DESCRIPTIVE.get(node.type().name().split("::")[0])
    parm = node.parm(name) if name else None
    if parm is not None:
        try:
            # The editor shows the raw text: $F4 stays $F4.
            text = parm.unexpandedString()
        except hou.Error:
            text = parm.evalAsString()
        # The editor shows only the file name of a file path.
        if parm.parmTemplate().stringType() == hou.stringParmType.FileReference:
            text = text.replace("\\", "/").rsplit("/", 1)[-1]
        if text:
            lines.append(text)
    # The editor truncates comment and path text (preference: truncated).
    return lines[:1] + [line if len(line) <= TRUNCATE else line[:TRUNCATE - 3] + "..."
                        for line in lines[1:]]


def box(item, full=True):
    """[x0, y0, x1, y1] of what the editor draws for an item, text included.
    Without `full`, only the node and its name."""
    x, y = _pos(item)
    w, h = _size(item)
    lines = _text_lines(item)[:None if full else 1]
    if not lines:
        return [x, y, x + w, y + h]
    if item.parent().childTypeCategory() == hou.vopNodeTypeCategory():
        # A VOP node shows its name in its title bar.
        return [x, y, x + max(w, len(lines[0]) * CHAR), y + h + LINE]
    width = max(len(line) for line in lines) * CHAR
    # The type label sits above the name, in a smaller font.
    label = TYPE_LABEL if full else 0.0
    if full:
        width = max(width, len(item.type().description()) * CHAR * 0.85)
    return [x, min(y, y + h - LINE * len(lines)), x + w + 0.1 + width, y + h + label]


def _shape(item):
    """The node itself, without its text: what a wire must not pass behind."""
    x, y = _pos(item)
    w, h = _size(item)
    return [x, y, x + w, y + h]


def _notes(network, notes):
    """Put each sticky note where it was next to its node, or else in the
    first free place right of, left of, above or under that node."""
    taken = [box(node) for node in network.children()]
    for note, near, offset in notes:
        w, h = _size(note)
        x0, y0, x1, y1 = box(near)
        tries = [_pos(near) + offset, hou.Vector2(x1 + 0.3, y1 - h),
                 hou.Vector2(x0 - w - 0.3, y1 - h), hou.Vector2(x0, y1 + 0.3),
                 hou.Vector2(x0, y0 - h - 0.3)]
        right = max(t[2] for t in taken)
        tries.append(hou.Vector2(right + 0.5, y1 - h))
        for spot in tries:
            shape = (spot[0], spot[1], spot[0] + w, spot[1] + h)
            if not any(_overlap(shape, other, 0.1) for other in taken):
                break
        note.setPosition(spot)
        taken.append(_shape(note))


def _gap(a, b):
    """The distance between two boxes, 0 when they touch."""
    return math.hypot(max(0.0, a[0] - b[2], b[0] - a[2]), max(0.0, a[1] - b[3], b[1] - a[3]))


def _overlap(a, b, margin=0.0):
    return a[0] < b[2] + margin and b[0] < a[2] + margin and \
        a[1] < b[3] + margin and b[1] < a[3] + margin


def _out_point(item, output=0):
    x, y = _pos(item)
    if isinstance(item, hou.NetworkDot):
        return (x, y)
    w, h = _size(item)
    count = max(len(item.outputConnectors()), 1) if hasattr(item, "outputConnectors") else 1
    if not _vertical(item.parent()):
        # Outputs go down the right side.
        return (x + w, y + h - h * (min(output, count - 1) + 0.5) / count)
    if count == 1:
        return (x + w / 2.0, y)
    return (x + w * (min(output, count - 1) + 1) / (count + 1), y)


def _in_point(item, index=0):
    x, y = _pos(item)
    w, h = _size(item)
    if isinstance(item, hou.NetworkDot):
        return (x, y)
    count = max(len(item.inputConnectors()), 1) if hasattr(item, "inputConnectors") else 1
    if count > 64:
        # A node with any number of inputs (Merge, Switch) spreads the wires
        # that it has over its width.
        count = max([c.inputIndex() + 1 for c in item.inputConnections()] + [1])
    count = min(count, 8)
    index = min(index, count - 1)
    if not _vertical(item.parent()):
        # Inputs go down the left side.
        return (x, y + h - h * (index + 0.5) / count)
    return (x + w * (index + 1) / (count + 1), y + h)


def _crosses(p, q, rect):
    """True when the segment p-q passes through rect."""
    (x0, y0), (x1, y1) = p, q
    t0, t1 = 0.0, 1.0
    dx, dy = x1 - x0, y1 - y0
    for edge, delta in ((x0 - rect[0], -dx), (rect[2] - x0, dx),
                        (y0 - rect[1], -dy), (rect[3] - y0, dy)):
        # Liang-Barsky clipping of the segment against the box.
        if abs(delta) < 1e-12:
            if edge < 0:
                return False
            continue
        t = edge / delta
        if delta < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return t1 - t0 > 1e-6


def rounded(network):
    """True when the editor draws the wires of `network` as curves. Shift+S
    toggles it, and a preference sets it for new networks. The checks take
    the wires of a network that reads from left to right as straight."""
    if not _vertical(network):
        return False
    try:
        return network.connectionDrawStyle() == hou.nodeConnectionDrawStyle.Rounded
    except (hou.Error, AttributeError):
        return False


def wire_line(points, curved):
    """The line that the editor draws through `points` (output, dots, input),
    as a list of points, read from screen grabs of Houdini 22. A straight leg
    is a short stub down, a diagonal, and a short stub into the end. A rounded
    leg turns across just under its start, with a small corner, and turns
    down into its end with one wide arc: the across run sits near the
    source, not at the middle height."""
    line = [points[0]]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if abs(x1 - x0) < 1e-6:
            line.append((x1, y1))
        elif not curved:
            line += [(x0, y0 - STUB), (x1, y1 + STUB), (x1, y1)]
        elif y1 < y0 - 1e-6:
            side = 1.0 if x1 > x0 else -1.0
            first = min(CORNER, abs(x1 - x0) / 2.0, (y0 - y1) / 2.0)
            run = y0 - first
            last = min(run - y1, abs(x1 - x0) - first)
            # A small quarter turn from down to across under the start.
            line += [(x0 + side * first * (1 - math.cos(a)), y0 - first * math.sin(a))
                     for a in [step * math.pi / 8.0 for step in range(5)]]
            # A wide quarter turn from across to down into the end.
            line += [(x1 - side * last * (1 - math.sin(b)), run - last * (1 - math.cos(b)))
                     for b in [step * math.pi / 16.0 for step in range(9)]]
            line.append((x1, y1))
        else:
            # The end sits above the start: down, across at the middle, up.
            middle = (y0 + y1) / 2.0
            radius = min(CORNER, abs(x1 - x0) / 2.0, abs(y1 - y0) / 2.0)
            side = 1.0 if x1 > x0 else -1.0
            turns = [step * math.pi / 8.0 for step in range(5)]
            line += [(x0 + side * radius * (1 - math.cos(a)),
                      middle - radius * (1 - math.sin(a))) for a in turns]
            line += [(x1 - side * radius * (1 - math.sin(a)),
                      middle + radius * (1 - math.cos(a))) for a in turns]
            line.append((x1, y1))
    return line


# ---------------------------------------------------------------------------
# The graph: wires between nodes, through dots.

def _source(item):
    """The node behind an item and the dots on the way."""
    dots = []
    while isinstance(item, hou.NetworkDot):
        dots.append(item)
        item = item.inputItem()
    return item, dots


def _wires(nodes):
    """[(source, output, reader, input, dots)] for every wire into `nodes` that
    comes from a node."""
    found = []
    for node in nodes:
        try:
            connections = node.inputConnections()
        except hou.Error:
            continue
        for connection in connections:
            source, dots = _source(connection.inputItem())
            if isinstance(source, hou.Node):
                found.append((source, connection.outputIndex(), node,
                              connection.inputIndex(), dots))
    return found


def _readers(node):
    """The nodes that read `node`, through dots."""
    found, todo = [], [node]
    while todo:
        item = todo.pop()
        for connection in item.outputConnections():
            other = connection.outputItem()
            if isinstance(other, hou.NetworkDot):
                todo.append(other)
            elif other not in found:
                found.append(other)
    return found


def _downstream(node):
    found, todo = set(), [node]
    while todo:
        for reader in _readers(todo.pop()):
            if reader not in found:
                found.add(reader)
                todo.append(reader)
    return found


def _vertical(network):
    """False for a VOP or a Copernicus network, which reads from left to right."""
    try:
        return network.childTypeCategory().name() not in ("Vop", "Cop")
    except (hou.Error, AttributeError):
        return True


def _terminal(node):
    name = node.type().name().lower()
    return node.name().upper().startswith("OUT") or name.startswith(TERMINAL) or \
        (hasattr(node, "isDisplayFlagSet") and node.isDisplayFlagSet()) or \
        (hasattr(node, "isRenderFlagSet") and node.isRenderFlagSet()) or \
        not node.outputConnectors()


# ---------------------------------------------------------------------------
# A whole layout: the Smart Layout shelf tool.

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


def _columns(nodes, depth):
    """Column of each node.

    A node sits in the column of its first input, so a chain reads straight
    down the page. The other inputs of a node start a new chain in the first
    free column to its right. Chains are walked up from the end nodes, the
    leftmost end node first, so that its chain is the trunk in column 0.
    """
    inside = set(nodes)
    column = {}
    used = {}      # column -> rows covered by the chains already put there

    def first_input(node):
        inputs = node.inputs()
        return inputs[0] if inputs else None

    def put(node, start):
        chain = [node]
        while True:
            parent = first_input(chain[-1])
            if parent is None or parent not in inside or parent in column or parent in chain:
                break
            chain.append(parent)
        top, bottom = min(depth[n] for n in chain), max(depth[n] for n in chain)
        rows = set(range(top, bottom + 1))
        # Keep one empty row to the next chain in the column, else the two
        # chains read as one.
        padded = set(range(top - 1, bottom + 2))
        col = start
        while used.get(col, set()) & padded:
            col += 1
        used.setdefault(col, set()).update(rows)
        for n in chain:
            column[n] = col
        for n in chain:
            for side in n.inputs()[1:]:
                if side is not None and side in inside and side not in column:
                    put(side, col + 1)

    def left_first(n):
        return (_pos(n)[0], -_pos(n)[1], n.name())

    ends = [n for n in nodes if not any(o in inside for o in n.outputs())]
    for node in sorted(ends, key=left_first) + sorted(nodes, key=left_first):
        if node not in column:      # the second list catches feedback loops
            put(node, 0)
    return column


def _moved_since(before):
    """{path: [old, new]} of the items in `before` that moved."""
    return {item.path(): [list(old), list(_pos(item))] for item, old in before.items()
            if (old - _pos(item)).length() > 1e-4}


def layout(parent=None, nodes=None, origin=None):
    """Place nodes on a grid: one row per input depth, each node in the column
    of its first input. Only the given nodes move, and their top-left corner
    stays unless `origin` gives it. A sticky note moves with the node nearest
    to it, and a network box fits around its nodes again.
    Returns {"moved": {path: [old, new]}}."""
    if nodes is None:
        if parent is None:
            raise ValueError("Give parent, a network, or nodes, a list of nodes.")
        nodes = list(parent.children())
    nodes = [node for node in nodes if isinstance(node, hou.Node)]
    if not nodes:
        return {"moved": {}}
    parent = nodes[0].parent()
    if not parent.isEditable():
        raise ValueError(f"{parent.path()} is inside a locked asset: its nodes cannot move.")
    before = {node: _pos(node) for node in nodes}
    if origin is None:
        origin = (min(p[0] for p in before.values()), max(p[1] for p in before.values()))
    notes = []
    for note in parent.stickyNotes():
        near = min(nodes, key=lambda node: _gap(box(node), _shape(note)))
        notes.append((note, near, note.position() - _pos(near)))

    depth = _depths(nodes)
    column = _columns(nodes, depth)
    if _vertical(parent):
        for node in nodes:
            node.setPosition(hou.Vector2(origin[0] + column[node] * COLUMN_STEP,
                                         origin[1] - depth[node] * ROW_STEP))
    else:
        # A VOP or COP network reads from left to right: the same grid, turned.
        across = max(_size(node)[1] for node in nodes) + 0.5
        for node in nodes:
            node.setPosition(hou.Vector2(origin[0] + depth[node] * COLUMN_STEP,
                                         origin[1] - column[node] * across))

    moved = _moved_since(before)
    _notes(parent, notes)
    for frame in parent.networkBoxes():
        if any(item.path() in moved for item in frame.items() if isinstance(item, hou.Node)):
            frame.fitAroundContents()
    return {"moved": moved}


def run():
    """Shelf tool: lay out the selected nodes of the network under the cursor."""
    editor = hou.ui.paneTabUnderCursor()
    if not isinstance(editor, hou.NetworkEditor):
        editor = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
    network = editor.pwd()
    selected = [n for n in hou.selectedNodes() if n.parent() == network]
    if not selected:
        hou.ui.setStatusMessage("Smart Layout: select the nodes to lay out.",
                                hou.severityType.Warning)
        return
    with hou.undos.group("Smart Layout"):
        layout(nodes=selected)


# ---------------------------------------------------------------------------
# New nodes, in place.

SLOT_X = COLUMN_STEP * 0.9   # two nodes closer than this in x and y share a slot
SLOT_Y = ROW_STEP * 0.9


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
    down, to make room. Returns {path: [old, new]} of every node that moved,
    the new ones included."""
    nodes = [n for n in nodes if n is not None]
    if not nodes:
        return {}
    network = nodes[0].parent()
    before = {n: _pos(n) for n in network.children()}
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
    return _moved_since(before)


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


def insert(node, source, reader=None, output=0):
    """Put `node` on every wire from output `output` of `source` into `reader`
    (all three streams of a Vellum chain), or into every reader without
    `reader`, then place it: it takes the slot under the source, and the
    readers move down one row with what they feed (rule 3). Returns the moves
    and the rewired inputs."""
    targets = []
    for item in _readers(source):
        if reader is not None and item != reader:
            continue
        for s, out, r, index, _ in _wires([item]):
            if s == source and out == output:
                targets.append((r, index))
    if not targets:
        raise ValueError(f"No wire from {source.path()} output {output}"
                         + (f" to {reader.path()}" if reader is not None else "") + ".")
    node.setInput(0, source, output)
    for r, index in targets:
        r.setInput(index, node)
    return {"moved": place([node]),
            "rewired": [{"reader": r.path(), "input": index} for r, index in targets]}


def place_chain(chain, reader, index=0):
    """Wire `chain` (in order) into input `index` of `reader` and place it as a
    side chain: the next free column right, the last node one row above the
    reader (rule 5). Returns the moves."""
    chain = list(chain)
    for upper, lower in zip(chain, chain[1:]):
        if lower.input(0) != upper:
            lower.setInput(0, upper)
    reader.setInput(index, chain[-1])
    network = reader.parent()
    before = {n: _pos(n) for n in network.children()}
    inside = set(chain)
    # The chain may not rise above its sources outside it (rule 1): when the
    # room above the reader is too small, the reader and its graph move down.
    outside = [i for n in chain for i in n.inputs() if i is not None and i not in inside]
    if outside:
        need = min(_pos(i)[1] for i in outside) - ROW_STEP * (len(chain) + 1)
        _push_down(reader, min(_pos(reader)[1], need), skip=inside | set(outside))
    others = [n for n in network.children() if n not in inside]
    x = _pos(reader)[0] + COLUMN_STEP
    spots = [_pos(reader)[1] + ROW_STEP * (len(chain) - i) for i in range(len(chain))]
    while any(_occupied(x, y, others) for y in spots):
        x += COLUMN_STEP
    for node, y in zip(chain, spots):
        node.setPosition(hou.Vector2(x, y))
    return {"moved": _moved_since(before)}


# ---------------------------------------------------------------------------
# Faults.

def _label(item):
    return item.name() if isinstance(item, hou.Node) else f"a dot under {_source(item)[0].name()}"


def legs(network):
    """[((source item, output), reader item, line)] for every wire piece
    between two items (a node or a dot), as the editor draws it."""
    curved = rounded(network)
    found = []
    for item in list(network.children()) + list(network.networkDots()):
        try:
            connections = item.inputConnections()
        except hou.Error:
            continue
        for connection in connections:
            source, output = connection.inputItem(), connection.outputIndex()
            if source is None:
                continue
            start = _pos(source) if isinstance(source, hou.NetworkDot) else \
                _out_point(source, output)
            end = _pos(item) if isinstance(item, hou.NetworkDot) else \
                _in_point(item, connection.inputIndex())
            found.append(((source, output), item, wire_line([start, end], curved)))
    return found


def _runs(line):
    """The straight horizontal and vertical runs of a drawn line:
    (axis, level, low, high). Axis 0 is horizontal."""
    found = []
    for (x0, y0), (x1, y1) in zip(line, line[1:]):
        if abs(y1 - y0) < 1e-6 and abs(x1 - x0) > 0.05:
            found.append((0, y0, min(x0, x1), max(x0, x1)))
        elif abs(x1 - x0) < 1e-6 and abs(y1 - y0) > 0.05:
            found.append((1, x0, min(y0, y1), max(y0, y1)))
    return found


def _on_top(one, two, shared=None, runs=None):
    """True when two drawn lines share a stretch: the same direction, about
    the same level, and a common length. A long pair of parallel runs reads as
    one line from further apart. `shared` is the start point of two pieces
    from one output: the run down from it is one wire that splits. `runs`
    holds the runs of both lines when the caller has them."""
    first, second = runs or (_runs(one), _runs(two))
    if shared:
        def keep(run):
            return not (run[0] == 1 and abs(run[1] - shared[0]) < 1e-3 and
                        abs(run[3] - shared[1]) < 1e-3)
        first, second = [r for r in first if keep(r)], [r for r in second if keep(r)]
    for a in first:
        for b in second:
            common = min(a[3], b[3]) - max(a[2], b[2])
            if a[0] == b[0] and common > 0.15 and                     abs(a[1] - b[1]) < (0.2 if common > 1.5 else 0.1):
                return True
    return False


def overlaps(network, found=None):
    """Pairs of wire pieces that run on top of each other. Two pieces from one
    node read as one wire that splits, and two pieces into one node (the fan
    into a Merge) read as wires that join, so they are not a pair."""
    found = found if found is not None else legs(network)
    runs = [_runs(leg[2]) for leg in found]
    roots = [_source(leg[0][0])[0] for leg in found]
    pairs = []
    for i, one in enumerate(found):
        for j in range(i + 1, len(found)):
            two = found[j]
            if roots[i] != roots[j] and one[1] != two[1] and _on_top(one[2], two[2], one[2][0] if one[0] == two[0] else None,
                       (runs[i], runs[j])):
                pairs.append((one, two))
    return pairs


def problems(network, nodes=None):
    """Layout faults: a node above its input, drawn boxes that overlap (names,
    comments and path text included), a wire that passes behind a node, a
    dot that feeds nothing, and a node that feeds nothing and is not an end
    (an OUT_ or Output node, a node with the display or render flag, a ROP).
    With `nodes`, only the faults that involve one of them."""
    faults = []
    children = list(network.children())
    dots = list(network.networkDots())
    mine = set(nodes) if nodes else set(children) | set(dots)
    vertical = _vertical(network)
    curved = rounded(network)
    boxes = {item: box(item) for item in children}
    for source, output, reader, index, via in _wires(children):
        if not (reader in mine or source in mine):
            continue
        if vertical and _pos(reader)[1] > _pos(source)[1] - 0.2 and not via:
            faults.append(f"{reader.name()} is not below its input {source.name()}")
        # Each leg of the wire, through its dots.
        points = wire_line([_out_point(source, output)] + [_pos(dot) for dot in reversed(via)] +
                           [_in_point(reader, index)], curved)
        for p, q in zip(points, points[1:]):
            behind = next((item for item in children if item not in (source, reader) and
                           _crosses(p, q, _shape(item))), None)
            if behind is not None:
                faults.append(f"the wire {source.name()} -> {reader.name()} passes behind "
                              f"{behind.name()}")
                break
    for i, a in enumerate(children):
        for b in children[i + 1:]:
            if (a in mine or b in mine) and _overlap(boxes[a], boxes[b]):
                faults.append(f"{a.name()} and {b.name()} overlap: a name, a comment or a "
                              f"path covers the other")
    for one, two in overlaps(network):
        if one[1] in mine or two[1] in mine:
            faults.append(f"the wires into {_label(one[1])} and {_label(two[1])} run on top of "
                          f"each other")
    for note in network.stickyNotes():
        cover = next((node for node in children if node in mine and
                      _overlap(_shape(note), boxes[node])), None)
        if cover is not None:
            faults.append(f"the sticky note {note.name()} covers {cover.name()}")
    for dot in dots:
        if dot in mine and not dot.outputConnections():
            faults.append(f"the dot {dot.name()} feeds nothing")
    for node in children:
        if node in mine and node.outputConnectors() and not node.outputConnections() \
                and not _terminal(node):
            faults.append(f"{node.name()} feeds nothing and is not an OUT_ or Output node")
        if node in mine and node.comment():
            faults.append(f"{node.name()} has a node comment: put the text in a sticky note "
                          f"(node_edit mode note) and clear the comment")
    faults += _box_faults(network, children, None if nodes is None else mine)
    if network.childTypeCategory() == hou.sopNodeTypeCategory() and not any(
            node.type().name() == "output" for node in children):
        shown = next((node for node in children if node in mine and node.isDisplayFlagSet()), None)
        if shown is not None and shown.type().name() == "null" and \
                shown.name().upper().startswith("OUT"):
            faults.append(f"the display node {shown.name()} is a Null: end the network with "
                          f"one Output SOP named OUT_<NAME>; a Null OUT_ is for a result that "
                          f"another network reads")
    return faults


def _box_faults(network, children, mine=None):
    """A box title that is a sentence or that the editor cuts off, a box in a
    box, two boxes that overlap, and a node inside a box it is not part of.
    With `mine`, only the boxes that hold one of those nodes."""
    faults = []
    frames = list(network.networkBoxes())
    members = {frame: {item for item in frame.items() if isinstance(item, hou.Node)}
               for frame in frames}
    for frame in frames:
        if mine is not None and not members[frame] & mine:
            continue
        title = frame.comment()
        if len(title) > 24 or len(title.split()) > 3:
            faults.append(f"the box title {title[:40]!r} is a sentence: a title is one to three "
                          f"words, the text goes in a sticky note")
        elif len(title) * CHAR > _size(frame)[0]:
            faults.append(f"the editor cuts off the box title {title!r}: the box is too narrow")
        inner = frame.parentNetworkBox()
        if inner is not None:
            faults.append(f"the box {title or frame.name()!r} sits inside the box "
                          f"{inner.comment() or inner.name()!r}: never put a box in a box")
        for other in frames:
            if other != frame and other.name() > frame.name() and \
                    other != inner and other.parentNetworkBox() != frame and \
                    _overlap(_shape(frame), _shape(other)):
                faults.append(f"the boxes {title or frame.name()!r} and "
                              f"{other.comment() or other.name()!r} overlap")
        for node in children:
            if node not in members[frame] and _overlap(_shape(frame), _shape(node)) and \
                    not any(node in members[o] and _overlap(_shape(o), _shape(frame))
                            for o in frames if o != frame):
                faults.append(f"{node.name()} lies inside the box {title or frame.name()!r} "
                              f"but is not part of it")
    return faults
