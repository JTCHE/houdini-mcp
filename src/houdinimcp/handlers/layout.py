"""Readable layout for a Houdini node network, the way the user lays one out.

The rules come from networks that the user laid out by hand:

1. A chain reads straight down: a node sits under its first input, and that
   wire is one vertical line.
2. Side inputs come from the right, in port order: the source of input 1
   sits right of the source of input 0, input 2 further right. Wires do not
   cross.
3. A source (an IN_ Object Merge, a File) sits one row above its first
   reader, not at the top of the graph. A side chain ends one row above the
   node it feeds.
4. A second branch from a node goes in a column to the right.
5. A wire that skips rows, or that would pass behind a node, drops down a
   lane to the right of the nodes it passes, and turns into its reader
   through a dot that sits right of the reader, a little above its row. The
   readers of one source share its lane, one dot each. Lanes nest outward.
6. Spacing comes from what the editor draws: the node, its name, its
   displayed comment and its path text. Rows are 1.3 apart; a long comment
   takes more rows.
7. `place`, `insert` and `place_chain` never move a node that the user placed,
   except down, to clear an overlap or to make the room that a new node needs.
   They return every node that moved, with the old and the new position.

    layout(network)                 # every node
    layout(nodes=[...])             # only these nodes; the others stay
    place([new_node, ...])          # new nodes next to what they connect to
    insert(node, source, reader)    # a new node on the wires between two nodes
    place_chain([a, b, c], reader, input_index)
    problems(network)               # layout faults
"""
import math

import hou

ROW = 1.3            # vertical distance between two rows
GAP = 0.45           # free space between the drawn boxes of two columns
CHAR = 0.12          # width of one character of drawn text
LINE = 0.25          # height of one line of drawn text
DOT_ABOVE = 0.55     # a lane dot sits this far above the row of its reader
LANE = 0.8           # width of a lane column
COLUMN_STEP = 3.6    # a sibling column when nothing else decides
# Long wires skip more rows than this before they take a lane.
SKIP = 2
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
            text = parm.evalAsString()
        except hou.Error:
            text = ""
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
    width = max(len(line) for line in lines) * CHAR
    return [x, min(y, y + h - LINE * len(lines)), x + w + 0.1 + width, y + h]


def _shape(item):
    """The node itself, without its text: what a wire must not pass behind."""
    x, y = _pos(item)
    w, h = _size(item)
    return [x, y, x + w, y + h]


def _overlap(a, b, margin=0.0):
    return a[0] < b[2] + margin and b[0] < a[2] + margin and \
        a[1] < b[3] + margin and b[1] < a[3] + margin


def _out_point(item, output=0):
    x, y = _pos(item)
    if isinstance(item, hou.NetworkDot):
        return (x, y)
    w, _ = _size(item)
    count = max(len(item.outputConnectors()), 1) if hasattr(item, "outputConnectors") else 1
    if count == 1:
        return (x + w / 2.0, y)
    return (x + w * (min(output, count - 1) + 1) / (count + 1), y)


def _in_point(item, index=0):
    x, y = _pos(item)
    w, h = _size(item)
    if isinstance(item, hou.NetworkDot):
        return (x, y)
    count = max(len(item.inputConnectors()), 1) if hasattr(item, "inputConnectors") else 1
    count = min(count, 8)
    index = min(index, count - 1)
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
    toggles it, and a preference sets it for new networks."""
    try:
        return network.connectionDrawStyle() == hou.nodeConnectionDrawStyle.Rounded
    except (hou.Error, AttributeError):
        return False


def wire_line(points, curved):
    """The line that the editor draws through `points` (output, dots, input),
    as a list of points. A curved leg leaves its start straight down and comes
    into its end from straight above."""
    if not curved:
        return list(points)
    line = [points[0]]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        # ponytail: the bend of the Houdini curve is a guess (half the height,
        # at least 0.5). Match it to the editor if a grab ever disagrees.
        bend = max(abs(y1 - y0) * 0.5, 0.5)
        for step in range(1, 17):
            t = step / 16.0
            a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
            line.append(((a + b) * x0 + (c + d) * x1,
                         a * y0 + b * (y0 - bend) + c * (y1 + bend) + d * y1))
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
    """False for a VOP network, which reads from left to right."""
    try:
        return network.childTypeCategory() != hou.vopNodeTypeCategory()
    except (hou.Error, AttributeError):
        return True


def _extra_rows(node):
    """Rows under a node that its text takes."""
    lines = len(_text_lines(node))
    height = LINE * lines - _size(node)[1]
    return max(0, int(math.ceil((height - 0.45 * ROW) / ROW)))


def _terminal(node):
    name = node.type().name().lower()
    return node.name().upper().startswith("OUT") or name.startswith(TERMINAL) or \
        (hasattr(node, "isDisplayFlagSet") and node.isDisplayFlagSet()) or \
        (hasattr(node, "isRenderFlagSet") and node.isRenderFlagSet()) or \
        not node.outputConnectors()


# ---------------------------------------------------------------------------
# A whole layout.

def _ranks(nodes, wires):
    """Row of each node: under every input. A source, and a side chain (one
    that ends in a side input), are pulled down to one row above their
    nearest reader, so they sit next to their use. A main chain hangs from
    its top, in one piece."""
    inputs = {node: [] for node in nodes}
    readers = {node: [] for node in nodes}
    port = {}
    for source, _, reader, index, _ in wires:
        if source in inputs and reader in inputs and source != reader:
            inputs[reader].append(source)
            readers[source].append(reader)
            port[source, reader] = min(index, port.get((source, reader), index))
    extra = {node: _extra_rows(node) for node in nodes}
    rank, order, state = {}, [], {}

    def visit(node):
        if state.get(node) == 2:
            return
        if state.get(node) == 1:      # a loop: leave it where it stops
            return
        state[node] = 1
        for source in inputs[node]:
            visit(source)
        state[node] = 2
        order.append(node)

    for node in nodes:
        visit(node)
    for node in order:
        rank[node] = max([rank[s] + 1 + extra[s] for s in inputs[node] if s in rank] or [0])
    pulled = {}
    for node in reversed(order):
        below = [rank[r] for r in readers[node] if r in rank]
        pulled[node] = bool(below) and (not inputs[node] or all(
            port[node, r] > 0 or pulled.get(r) for r in readers[node]))
        if pulled[node]:
            rank[node] = max(rank[node], min(below) - 1 - extra[node])
    top = min(rank.values())
    return {node: value - top for node, value in rank.items()}, inputs, readers, extra


def _main_sink(sinks, rank):
    def score(node):
        name = node.type().name()
        return (name == "output" or node.name().upper().startswith("OUT"),
                bool(getattr(node, "isDisplayFlagSet", lambda: False)()),
                rank[node], -_pos(node)[0])
    return max(sinks, key=score)


def _components(nodes, inputs, readers):
    left, groups = set(nodes), []
    for node in nodes:
        if node not in left:
            continue
        group, todo = [], [node]
        left.discard(node)
        while todo:
            current = todo.pop()
            group.append(current)
            for other in inputs[current] + readers[current]:
                if other in left:
                    left.discard(other)
                    todo.append(other)
        groups.append(group)
    return groups


def _columns(group, rank, inputs, readers, extra, wires):
    """Column of each node of one connected group, and the lanes.

    The main output goes in column 0; every node is put above it through its
    inputs, the first input in the same column, side inputs to the right.
    """
    rows = {node: set(range(rank[node], rank[node] + 1 + extra[node])) for node in group}
    used = {}
    column = {}
    ports = {}
    for source, _, reader, index, _ in wires:
        if reader in rows and source in rows:
            ports.setdefault(reader, []).append((index, source))

    # The reader that continues the chain of each node: the reader through
    # input 0 with the longest input 0 chain under it, so a branch that turns
    # into a side input does not take the column; then the one that leads to
    # the most nodes; the nearest one on a tie.
    # A source sits above its nearest reader. A reader that also feeds
    # another reader of the same node is a branch to the side.
    below = {}

    def downstream(node):
        if node not in below:
            below[node] = set()
            found = set()
            for r in readers[node]:
                if r in rows:
                    found |= {r} | downstream(r)
            below[node] = found
        return below[node]

    candidates = {}
    for reader, pairs in ports.items():
        for index, source in pairs:
            if not index:
                candidates.setdefault(source, []).append(reader)
    straight = {}

    def chain(node):
        """How many nodes continue from `node` through input 0 wires: the
        length of the straight column under it."""
        if node not in straight:
            straight[node] = 0
            straight[node] = max([1 + chain(r) for r in candidates.get(node, [])] or [0])
        return straight[node]

    owner = {}
    for source, found in candidates.items():
        ends = [r for r in found if not any(o in downstream(r) for o in found if o != r)] \
            or found
        if not inputs[source]:
            owner[source] = min(ends, key=lambda r: rank[r])
        else:
            owner[source] = min(ends, key=lambda r: (-chain(r), -len(downstream(r)), rank[r]))

    strict = [True]

    def free(col, cells):
        return not (used.get(col, set()) & cells)

    def take(node, col):
        column[node] = col
        used.setdefault(col, set()).update(rows[node])

    def first_free(start, cells):
        col = start
        while not free(col, cells):
            col += 1
        return col

    def grow(node):
        """Place the inputs that are not placed yet, above `node`. Returns the
        rightmost column that `node` and what it placed use."""
        right = column[node]
        for index, source in sorted(ports.get(node, []), key=lambda pair: pair[0]):
            # Placed already (a source with more readers), or a loop.
            if source in column or rank[source] >= rank[node]:
                continue
            # A node goes above the reader that continues its chain, so a
            # side input does not take it from there.
            if strict[0] and owner.get(source, node) != node:
                continue
            start = column[node] if index == 0 else right + 1
            # The column holds the source and every row down to its reader,
            # so the wire into the reader passes no node.
            cells = set(range(rank[source], rank[node]))
            col = first_free(start, cells | rows[source])
            take(source, col)
            used[col].update(cells)
            right = max(right, grow(source))
        return right

    sinks = [node for node in group if not [r for r in readers[node] if r in rows]]
    main = _main_sink(sinks, rank)
    take(main, 0)
    grow(main)
    # The other ends: under their first input when the column is free there,
    # else in the next free column to its right.
    for sink in sorted([s for s in sinks if s != main], key=rank.get):
        if sink in column:
            continue
        sources = [s for i, s in sorted(ports.get(sink, []), key=lambda p: p[0]) if s in column]
        start = column[sources[0]] if sources else 0
        take(sink, first_free(start, rows[sink]))
        grow(sink)
    # A node whose chain reader was never reached: above any placed reader.
    strict[0] = False
    for node in list(column):
        grow(node)
    # A node that only a loop reaches.
    for node in group:
        if node not in column:
            take(node, first_free(0, rows[node]))
    return column, used


def _column_x(group, column, used, rank, extra, left):
    """The x of each column. A column keeps clear of what the columns on its
    left draw in the rows that it uses: its nodes and the wires that run down
    it. A long name or path in a row far away does not push it."""
    drawn = {}        # column -> [(rows, width)] of its nodes, text included
    for node in group:
        b = box(node)
        rows = set(range(rank[node], rank[node] + 1 + extra[node]))
        drawn.setdefault(column[node], []).append((rows, b[2] - b[0]))
    xs = {}
    for col in range(max(column.values()) + 1):
        mine = used.get(col, set())
        x = xs[col - 1] + LANE if col else left
        for other in range(col):
            near = {r + d for r in mine for d in (-1, 0, 1)}
            for rows, width in drawn.get(other, []):
                if rows & near:
                    x = max(x, xs[other] + width + GAP)
            if used.get(other, set()) & mine:
                # A wire runs down that column in these rows.
                x = max(x, xs[other] + _NODE_WIDTH + GAP)
        xs[col] = x
    return xs


_NODE_WIDTH = 1.13


def layout(parent=None, nodes=None, origin=None):
    """Lay out `nodes` (default: every node of `parent`). The top-left corner of
    what moves stays where it was, unless `origin` gives it. Returns
    {"moved": {path: [old, new]}, "dots": {"made": n, "removed": n}}."""
    if nodes is None:
        if parent is None:
            raise ValueError("Give parent, a network, or nodes, a list of nodes.")
        nodes = list(parent.children())
    nodes = [node for node in nodes if isinstance(node, hou.Node)]
    if not nodes:
        return {"moved": {}, "dots": {"made": 0, "removed": 0}}
    parent = nodes[0].parent()
    vertical = _vertical(parent)
    before = {node: _pos(node) for node in nodes}
    if origin is None:
        origin = (min(p[0] for p in before.values()), max(p[1] for p in before.values()))
    wires = _wires(nodes)
    inside = set(nodes)
    rank, inputs, readers, extra = _ranks(nodes, wires)

    left = origin[0]
    for group in sorted(_components(nodes, inputs, readers),
                        key=lambda g: min(before[n][0] for n in g)):
        column, used = _columns(group, rank, inputs, readers, extra, wires)
        if vertical:
            xs = _column_x(group, column, used, rank, extra, left)
            for node in group:
                node.setPosition(hou.Vector2(xs[column[node]], origin[1] - rank[node] * ROW))
            left = max(box(node)[2] for node in group) + COLUMN_STEP
        else:
            # A VOP network reads left to right: rows become columns.
            heights, widths = {}, {}
            for node in group:
                w, h = _size(node)
                widths[rank[node]] = max(widths.get(rank[node], 0.0), w + 1.0)
                heights[column[node]] = max(heights.get(column[node], 0.0), h + 0.6)
            xs, x = {}, origin[0]
            for r in range(max(rank.values()) + 1):
                xs[r] = x
                x += widths.get(r, 1.0)
            ys, y = {}, origin[1] if left == origin[0] else origin[1] - left
            for col in range(max(column.values()) + 1):
                ys[col] = y
                y -= heights.get(col, 1.0)
            for node in group:
                node.setPosition(hou.Vector2(xs[rank[node]], ys[column[node]] - _size(node)[1]))
            left += origin[1] - y + 2.0
    dots = _route(wires, inside) if vertical else {"made": 0, "removed": 0}
    moved = {node.path(): [list(before[node]), list(_pos(node))] for node in nodes
             if (before[node] - _pos(node)).length() > 1e-4}
    return {"moved": moved, "dots": dots}


# ---------------------------------------------------------------------------
# Wires: straight when they can be, else down a lane through dots.

def _blocked(line, skip):
    """The first node whose shape the drawn `line` (a list of points) passes
    through."""
    network_items = skip[0].parent().children() if skip else ()
    for item in network_items:
        if item in skip:
            continue
        rect = _shape(item)
        rect = [rect[0] - 0.05, rect[1] - 0.05, rect[2] + 0.05, rect[3] + 0.05]
        if any(_crosses(p, q, rect) for p, q in zip(line, line[1:])):
            return item
    return None


def _route(wires, inside):
    """Wire each reader in `inside` to its source: straight when the wire
    skips at most SKIP rows and passes behind no node, else through a lane
    of dots right of the nodes it passes. Old dots on these wires that feed
    nothing after are removed."""
    if not wires:
        return {"made": 0, "removed": 0}
    network = wires[0][2].parent()
    curved = rounded(network)
    old = {dot for *_, dots in wires for dot in dots}
    lanes = {}
    for source, output, reader, index, dots in wires:
        if reader not in inside:
            continue
        p, q = _out_point(source, output), _in_point(reader, index)
        rows = (p[1] - q[1]) / ROW
        straight = (rows <= SKIP + 0.5 or abs(p[0] - q[0]) < 0.3) and \
            not _blocked(wire_line([p, q], curved), [source, reader] + list(old))
        if straight:
            if dots:
                reader.setInput(index, source, output)
            continue
        lanes.setdefault((source, output), []).append((reader, index))

    made = 0
    taken = []           # (x, y_top, y_bottom) of the lanes made so far
    for (source, output), targets in sorted(lanes.items(),
                                            key=lambda pair: -_pos(pair[0][0])[1]):
        targets.sort(key=lambda target: -_pos(target[0])[1])
        top = _out_point(source, output)[1]
        bottom = _pos(targets[-1][0])[1]
        # A source in the clear drops straight down at its own x. Else the
        # lane is the first vertical line right of the readers that passes no
        # drawn node and no other lane over these rows; lanes nest outward.
        own = _out_point(source, output)[0]
        readers = [t[0] for t in targets]
        span = [box(item, full=False) for item in network.children()
                if item != source and box(item)[1] <= top and box(item)[3] >= bottom - 0.5]
        x = own if all(own > box(r, full=False)[2] + 0.2 for r in readers) else \
            max(box(r, full=False)[2] for r in readers) + GAP
        for _ in range(200):
            hit = [b[2] for b in span if b[0] - 0.2 <= x <= b[2] + 0.2]
            hit += [lane[0] for lane in taken
                    if abs(lane[0] - x) < 0.5 and lane[2] < top and lane[1] > bottom]
            if not hit:
                break
            x = max(hit) + GAP
        taken.append((x, top, bottom))
        feed = source
        if abs(x - own) > 0.05:
            # Out to the lane between two rows, where no node sits, then down.
            turn = network.createNetworkDot()
            turn.setPosition(hou.Vector2(x, _pos(source)[1] - ROW * 0.5))
            turn.setInput(source, output)
            feed = turn
            made += 1
        for reader, index in targets:
            dot = network.createNetworkDot()
            dot.setPosition(hou.Vector2(x, _pos(reader)[1] + _size(reader)[1] + DOT_ABOVE))
            if feed == source:
                dot.setInput(source, output)
            else:
                dot.setInput(feed)
            reader.setInput(index, dot)
            feed = dot
            made += 1
    # A dot that fed only another old dot feeds nothing after that one goes.
    removed, left = 0, set(old)
    while True:
        dead = {dot for dot in left if not dot.outputConnections()}
        if not dead:
            break
        for dot in dead:
            dot.destroy()
        removed += len(dead)
        left -= dead
    return {"made": made, "removed": removed}


# ---------------------------------------------------------------------------
# New nodes among the nodes of the user.

def _others(node, skip=()):
    return [item for item in list(node.parent().children()) + list(node.parent().networkDots())
            if item != node and item not in skip]


def _free(item, x, y, others):
    """True when `item` at (x, y) covers nothing that the editor draws."""
    old = _pos(item)
    item.setPosition(hou.Vector2(x, y))
    mine = box(item)
    item.setPosition(old)
    return not any(_overlap(mine, box(other), 0.15) for other in others)


def _column_step(item):
    b = box(item)
    return max(COLUMN_STEP, b[2] - b[0] + GAP)


def _push(start, delta, moved, skip=()):
    """Move `start` and every node it feeds down by `delta`, then push down
    every other node that the moved ones now cover. Records old positions."""
    todo = [item for item in start if item not in skip]
    shifted = set()
    while todo:
        item = todo.pop()
        if item in shifted:
            continue
        shifted.add(item)
        moved.setdefault(item, _pos(item))
        item.setPosition(_pos(item) - hou.Vector2(0.0, delta))
    # Clear the overlaps that the move made, one pass at a time.
    for _ in range(50):
        hit = None
        for item in shifted:
            for other in _others(item, shifted):
                if _overlap(box(item), box(other), 0.1) and _pos(other)[1] <= _pos(item)[1]:
                    hit = other
                    break
            if hit:
                break
        if hit is None:
            break
        step = box(hit)[3] - min(box(item)[1] for item in shifted
                                  if _overlap(box(item), box(hit), 0.1)) + 0.2
        group = {hit} | (_downstream(hit) - shifted)
        for item in group:
            moved.setdefault(item, _pos(item))
            item.setPosition(_pos(item) - hou.Vector2(0.0, step))
        shifted |= group


def _report(moved):
    return {item.path(): [list(old), list(_pos(item))] for item, old in moved.items()
            if (old - _pos(item)).length() > 1e-4}


def place(nodes):
    """Place new nodes next to the nodes they connect to: under the first
    input, in its column when the room is free, else in the next free column
    to the right; a node with no input one row above its first reader. A
    reader of a new node moves down when the new node needs its room, and
    the nodes it covers then move down too. Returns {path: [old, new]} of
    every node that moved, the new ones included."""
    nodes = [node for node in nodes if node is not None]
    moved = {}
    pending = set(nodes)
    rank, _, _, _ = _ranks(nodes, _wires(nodes)) if nodes else ({}, 0, 0, 0)
    for node in sorted(nodes, key=lambda n: rank.get(n, 0)):
        pending.discard(node)
        moved.setdefault(node, _pos(node))
        others = _others(node, pending)
        parents = [s for s, _, r, i, _ in sorted(_wires([node]), key=lambda w: w[3])
                   if s not in pending]
        readers = [r for r in _readers(node) if r not in pending]
        if parents:
            x = _pos(parents[0])[0]
            y = min(_pos(p)[1] - _extra_rows(p) * ROW for p in parents) - ROW
        elif readers:
            reader = max(readers, key=lambda r: _pos(r)[1])
            x = _pos(reader)[0] + _column_step(reader)
            y = _pos(reader)[1] + ROW
        else:
            items = [item for item in others if isinstance(item, hou.Node)]
            if items:
                lowest = min(items, key=lambda item: _pos(item)[1])
                x, y = _pos(lowest)[0], _pos(lowest)[1] - ROW
            else:
                x, y = 0.0, 0.0
        # Readers of the node are its business: they move down, not it.
        blocking = [item for item in others if item not in readers and
                    item not in _downstream(node)]
        while not _free(node, x, y, blocking):
            x += COLUMN_STEP
        node.setPosition(hou.Vector2(x, y))
        for reader in readers:
            need = _pos(reader)[1] - (y - ROW - _extra_rows(node) * ROW)
            if need > 1e-4 and reader not in nodes:
                _push([reader] + list(_downstream(reader)), need, moved, skip=set(nodes))
    return _report(moved)


def insert(node, source, reader=None, output=0):
    """Put `node` on every wire from output `output` of `source` into `reader`
    (all three streams of a Vellum chain), or into every reader without
    `reader`. The node goes under the source; the readers and what they feed
    move down by the room that the node needs, and nothing else moves unless
    it is covered. Returns the moves and the rewired inputs."""
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
    moved = {node: _pos(node)}
    x = _pos(source)[0]
    y = _pos(source)[1] - ROW - _extra_rows(source) * ROW
    readers = {r for r, _ in targets}
    below = set(readers)
    for r in readers:
        below |= _downstream(r)
    others = [item for item in _others(node) if item not in below]
    while not _free(node, x, y, others):
        x += COLUMN_STEP
    node.setPosition(hou.Vector2(x, y))
    for r in sorted(readers, key=lambda item: -_pos(item)[1]):
        need = _pos(r)[1] - (y - ROW - _extra_rows(node) * ROW)
        if need > 1e-4:
            _push([r] + list(_downstream(r)), need, moved, skip={node, source})
    return {"moved": _report(moved),
            "rewired": [{"reader": r.path(), "input": index} for r, index in targets]}


def place_chain(chain, reader, index=0):
    """Wire `chain` (in order) into input `index` of `reader` and place it as a
    side chain: its own column right of the reader and of the sources of the
    lower inputs, the last node one row above the reader, rows 1.3 apart.
    When the column does not fit under the sources of the chain, the reader
    and what it feeds move down by the room it needs. Wires from far sources
    go down lanes through dots. Returns the moves and the dots."""
    chain = list(chain)
    for upper, lower in zip(chain, chain[1:]):
        if lower.input(0) != upper:
            lower.setInput(0, upper)
    reader.setInput(index, chain[-1])
    moved = {node: _pos(node) for node in chain}
    # Sources of the chain from outside it: the chain may not rise past them.
    outside = [s for s, _, r, _, _ in _wires(chain) if s not in chain]
    heights = [ROW * (1 + _extra_rows(node)) for node in chain]
    need = sum(heights)
    if outside:
        lowest = min(_pos(s)[1] - _extra_rows(s) * ROW for s in outside)
        room = lowest - _pos(reader)[1]
        if room < need + ROW * 0.5:
            _push([reader] + list(_downstream(reader)), need + ROW - room, moved,
                  skip=set(chain) | set(outside))
    lower = [s for s, _, r, i, _ in _wires([reader]) if i < index and s not in chain]
    x = max([_pos(reader)[0]] + [_pos(s)[0] for s in lower]) + max(
        [_column_step(reader)] + [_column_step(s) for s in lower])
    others = _others(chain[0], set(chain))
    while True:
        y, spots = _pos(reader)[1], []
        for node, height in zip(reversed(chain), reversed(heights)):
            y += height
            spots.append((node, x, y))
        if all(_free(node, sx, sy, others) for node, sx, sy in spots):
            break
        x += COLUMN_STEP
    for node, sx, sy in spots:
        node.setPosition(hou.Vector2(sx, sy))
    dots = _route(_wires(chain + [reader]), set(chain) | {reader})
    return {"moved": _report(moved), "dots": dots}


# ---------------------------------------------------------------------------
# Faults.

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
    for dot in dots:
        if dot in mine and not dot.outputConnections():
            faults.append(f"the dot {dot.name()} feeds nothing")
    for node in children:
        if node in mine and node.outputConnectors() and not node.outputConnections() \
                and not _terminal(node):
            faults.append(f"{node.name()} feeds nothing and is not an OUT_ or Output node")
    return faults
