"""Measures that compare two geometries: a fingerprint before and after a
change, edge stretch against a rest mesh, points inside a closed mesh, and
the places where surfaces cross."""
import hashlib
import itertools

import hou
import numpy as np

from . import timing
from .geometry import resolve, run_as_node

# Fingerprints that a caller saved by name, to compare with after a change.
PRINTS = {}
# Edge lists of rest meshes, by (path, points, prims, vertices).
_EDGES = {}


def _positions(geometry):
    return np.frombuffer(geometry.pointFloatAttribValuesAsString("P"),
                         dtype=np.float32).reshape(-1, 3).astype(np.float64)


def _round(values, digits=4):
    return [round(float(value), digits) for value in values]


def _clusters(points, most=5):
    """The groups of `points` (N x 3), biggest first: the points that fall in
    one cell of a grid of 5 cells across their box, with their center."""
    if not len(points):
        return []
    low = points.min(0)
    cell = max(float((points.max(0) - low).max()) / 5.0, 1e-6)
    keys = np.floor((points - low) / cell).astype(np.int64)
    _, inverse, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.ravel()
    return [{"count": int(counts[key]), "center": _round(points[inverse == key].mean(0))}
            for key in np.argsort(-counts)[:most]]


# ---------------------------------------------------------------------------
# Fingerprint: did a refactor keep the result?

def _fingerprint(path, frame):
    node, geometry = resolve(path, frame)
    names = sorted(f"{kind}:{attribute.name()}" for kind, attributes in (
        ("point", geometry.pointAttribs()), ("prim", geometry.primAttribs()),
        ("vertex", geometry.vertexAttribs()), ("detail", geometry.globalAttribs()))
        for attribute in attributes)
    box = geometry.boundingBox()
    return {"points": len(geometry.points()), "prims": len(geometry.prims()),
            "bounds": [_round(box.minvec()), _round(box.maxvec())],
            "P_hash": hashlib.sha1(geometry.pointFloatAttribValuesAsString("P")).hexdigest()[:16],
            "attribs_hash": hashlib.sha1("\n".join(names).encode()).hexdigest()[:16],
            "attribs": names}


def fingerprint(paths, frames=None, name=None, against=None, renamed=None):
    """For each node and frame: counts, bounds, a hash of P and of the
    attribute names. `name` keeps the result for a later call; `against`
    compares with the result kept under that name, and `renamed` maps an old
    path to its new one."""
    wanted = timing.frame_list(frames, [hou.frame()])
    found = {path: {str(frame): _fingerprint(path, frame) for frame in wanted}
             for path in paths}
    report = {"frames": wanted, "fingerprints": {
        path: {frame: {key: value for key, value in one.items() if key != "attribs"}
               for frame, one in by_frame.items()} for path, by_frame in found.items()}}
    if name:
        PRINTS[name] = found
        report["saved_as"] = name
    if against:
        if against not in PRINTS:
            raise ValueError(f"No fingerprint saved as '{against}'. Saved: "
                             f"{', '.join(PRINTS) or 'none'}. Save one with name=.")
        report["compare"] = _compare(PRINTS[against], found, renamed or {})
    return report


def _compare(old, new, renamed):
    differences = []
    for old_path, by_frame in old.items():
        path = renamed.get(old_path, old_path)
        if path not in new:
            differences.append(f"{old_path}: not read in this call (give it in path, or map "
                               f"it in renamed).")
            continue
        for frame, before in by_frame.items():
            after = new[path].get(frame)
            if after is None:
                differences.append(f"{path}: frame {frame} not read in this call.")
                continue
            for key in ("points", "prims", "bounds", "P_hash"):
                if before[key] != after[key]:
                    differences.append(f"{path} @ {frame}: {key} {before[key]} -> {after[key]}")
            if before["attribs"] != after["attribs"]:
                gone = sorted(set(before["attribs"]) - set(after["attribs"]))
                added = sorted(set(after["attribs"]) - set(before["attribs"]))
                differences.append(f"{path} @ {frame}: attributes removed {gone or 'none'}, "
                                   f"added {added or 'none'}")
    return {"same": not differences, "differences": differences}


# ---------------------------------------------------------------------------
# Stretch: edge lengths against a rest mesh with the same topology.

def _edges(path, geometry):
    key = (path, len(geometry.points()), len(geometry.prims()),
           geometry.intrinsicValue("vertexcount"))
    if key not in _EDGES:
        pairs = set()
        for prim in geometry.prims():
            points = [vertex.point().number() for vertex in prim.vertices()]
            closed = len(points) > 2 and (not isinstance(prim, hou.Face) or prim.isClosed())
            ring = zip(points, points[1:] + points[:1]) if closed else zip(points, points[1:])
            pairs.update((a, b) if a < b else (b, a) for a, b in ring)
        if len(_EDGES) > 8:
            _EDGES.clear()
        _EDGES[key] = np.array(sorted(pairs), dtype=np.int64).reshape(-1, 2)
    return _EDGES[key]


def stretch(path, against, threshold=None, limit=None):
    """How much each edge of `path` grew against the same edge on the rest
    mesh `against`: 0.1 is 10 % longer."""
    threshold = 0.1 if threshold is None else threshold
    _, rest = resolve(against)
    _, geometry = resolve(path)
    if len(rest.points()) != len(geometry.points()):
        raise ValueError(f"{path} has {len(geometry.points())} points and {against} has "
                         f"{len(rest.points())}. Stretch needs the same topology.")
    edges = _edges(against, rest)
    if not len(edges):
        raise ValueError(f"{against} has no edges: it holds no polygons or curves.")
    before, after = _positions(rest), _positions(geometry)
    rest_length = np.linalg.norm(before[edges[:, 0]] - before[edges[:, 1]], axis=1)
    keep = rest_length > 1e-9
    edges, rest_length = edges[keep], rest_length[keep]
    growth = np.linalg.norm(after[edges[:, 0]] - after[edges[:, 1]], axis=1) / rest_length - 1.0
    middle = (before[edges[:, 0]] + before[edges[:, 1]]) / 2.0
    over = growth > threshold
    worst = np.argsort(-growth)[:limit or 10]
    return {"edges": int(len(edges)), "max": round(float(growth.max()), 4),
            "min": round(float(growth.min()), 4),
            "percentiles": dict(zip(("50", "90", "99"),
                                    _round(np.percentile(growth, [50, 90, 99])))),
            "threshold": threshold, "over_threshold": int(over.sum()),
            "worst": [{"growth": round(float(growth[index]), 4),
                       "points": [int(point) for point in edges[index]],
                       "rest_middle": _round(middle[index])} for index in worst],
            "clusters_over_threshold": _clusters(middle[over]),
            "note": "Growth is the length on path over the rest length, minus 1. Positions "
                    "are on the rest mesh."}


# ---------------------------------------------------------------------------
# Inside: points of one geometry inside a closed mesh.

INSIDE = """
float w = windingnumber(1, @P);
i@__inside = abs(w) > 0.5;
f@__depth = i@__inside ? xyzdist(1, @P) : 0.0;
"""


def inside(path, against, threshold=None):
    """The points of `path` inside the closed mesh `against`, and how deep."""
    _, geometry = resolve(path)
    _, mesh = resolve(against)
    result = run_as_node("attribwrangle", {"snippet": INSIDE}, [geometry, mesh], "inside")
    flags = np.array(result.pointIntAttribValues("__inside"), dtype=bool)
    depth = np.array(result.pointFloatAttribValues("__depth"))
    points = _positions(result)
    report = {"points": int(len(flags)), "inside": int(flags.sum())}
    if flags.any():
        report["max_depth"] = round(float(depth[flags].max()), 4)
        report["center"] = _round(points[flags].mean(0))
        report["clusters"] = _clusters(points[flags])
    if threshold is not None:
        report["deeper_than"] = {"distance": threshold, "count": int((depth > threshold).sum())}
    return report


# ---------------------------------------------------------------------------
# Crossings: where surfaces pass through each other.

def crossings(path, against=None, split_by=None):
    """The points where the surfaces of `path` cross each other or cross
    `against`, counted for each pair of parts. A part is a value of the prim
    attribute `split_by`, else the whole node."""
    parts = _parts(resolve(path)[1], split_by, path)
    pairs = [((name, name), [one]) for name, one in parts.items()]
    pairs += [((a, b), [parts[a], parts[b]]) for a, b in itertools.combinations(parts, 2)]
    if against:
        body = resolve(against)[1]
        pairs += [((name, against), [one, body]) for name, one in parts.items()]
    found = []
    for (a, b), inputs in pairs:
        points = _crossing_points(inputs)
        if len(points):
            found.append({"pair": f"{a} x {b}", "count": int(len(points)),
                          "clusters": _clusters(points, 3)})
    found.sort(key=lambda pair: -pair["count"])
    return {"parts": list(parts), "pairs": found,
            "note": "A part with itself is a self crossing. A pair that is not listed has "
                    "no crossing."}


def _parts(geometry, split_by, name, most=20):
    """The geometry cut into one geometry for each value of `split_by`."""
    if not split_by:
        return {name: geometry}
    attribute = geometry.findPrimAttrib(split_by)
    if attribute is None:
        raise ValueError(f"{name} has no prim attribute '{split_by}'.")
    values = (geometry.primStringAttribValues(split_by)
              if attribute.dataType() == hou.attribData.String
              else geometry.primIntAttribValues(split_by))
    kinds = sorted(set(values))
    if len(kinds) > most:
        raise ValueError(f"'{split_by}' has {len(kinds)} values; crossings pairs at most "
                         f"{most} parts. Use an attribute with fewer values.")
    parts = {}
    for kind in kinds:
        part = hou.Geometry()
        part.merge(geometry)
        part.deletePrims([prim for prim, value in zip(part.prims(), values) if value != kind])
        parts[f"{split_by}={kind}"] = part
    return parts


def _crossing_points(inputs):
    """The crossing points of one geometry with itself, or of two geometries
    with each other (not the crossings inside one of them)."""
    verb = hou.sopNodeTypeCategory().nodeVerb("intersectionanalysis")
    verb.setParms({"useinputnumattrib": 1})
    found = hou.Geometry()
    verb.execute(found, inputs)
    points = _positions(found)
    if len(inputs) == 1 or not len(points):
        return points
    keep = [len(set(point.attribValue("sourceinput"))) > 1 for point in found.points()]
    return points[np.array(keep, dtype=bool)]


# ---------------------------------------------------------------------------
# Distance: how far each point is from another geometry.

DISTANCE = "f@__distance = xyzdist(1, @P);"


def distance(path, against, threshold=None, bins=None, limit=None):
    """The distance from each point of `path` to the surface of `against`: the
    extremes, a histogram, and the points farther than `threshold`."""
    from .volumes import _bins
    _, geometry = resolve(path)
    _, other = resolve(against)
    result = run_as_node("attribwrangle", {"snippet": DISTANCE}, [geometry, other], "distance")
    values = np.array(result.pointFloatAttribValues("__distance"))
    report = {"points": int(values.size), "against": against}
    if not values.size:
        return report
    counts, edges = np.histogram(values, bins=_bins(bins or 10))
    report.update({"min": round(float(values.min()), 4), "max": round(float(values.max()), 4),
                   "mean": round(float(values.mean()), 4),
                   "histogram": {"edges": _round(edges), "counts": counts.tolist()}})
    if threshold is not None:
        far = np.flatnonzero(values > threshold)
        report["farther_than"] = {"distance": threshold, "count": int(far.size),
                                  "points": far[:limit or 20].tolist(),
                                  "clusters": _clusters(_positions(result)[far])}
    return report


# ---------------------------------------------------------------------------
# Changes: what moves, grows or pops over a range of frames.

def changes(path, frames, attribs=None, threshold=None):
    """For each frame: the counts, the size and the center of the box, and the
    mean, min and max of each attribute of `attribs`. Then the frames where a
    number jumps by more than `threshold` (0.2, a ratio) from the frame before:
    the pops and the hard stops that one frame or a coarse sheet does not show.
    """
    wanted = timing.frame_list(frames)
    if len(wanted) < 2:
        raise ValueError('mode \'changes\' needs frames: two frames or more, for example '
                         '{"start": 1001, "end": 1100}.')
    rows = []
    with timing.keep_frame():
        for frame in wanted:
            hou.setFrame(frame)
            _, geometry = resolve(path)
            box = geometry.boundingBox()
            row = {"frame": frame, "points": len(geometry.points()),
                   "prims": len(geometry.prims()), "size": _round(box.sizevec()),
                   "center": _round(box.center())}
            for name in attribs or ():
                row[name] = _attribute_numbers(geometry, name)
            rows.append(row)
    ratio = 0.2 if threshold is None else threshold
    jumps = []
    for before, after in zip(rows, rows[1:]):
        scale = max(max(before["size"]), max(after["size"]), 1e-6)
        for key in ["points", "prims", "size", "center"] + list(attribs or ()):
            old, new = before[key], after[key]
            if isinstance(old, dict):
                old, new = old.get("mean"), new.get("mean")
            if old is None or new is None:
                continue
            old, new = np.atleast_1d(old).astype(float), np.atleast_1d(new).astype(float)
            # A position jumps against the size of the geometry, a count or a
            # value against itself.
            base = scale if key == "center" else np.maximum(np.maximum(abs(old), abs(new)), 1e-6)
            change = float((abs(new - old) / base).max())
            if change > ratio:
                jumps.append({"frame": after["frame"], "what": key, "from": before[key],
                              "to": after[key], "change": round(change, 3)})
    return {"path": path, "frames": rows, "jumps": jumps, "threshold": ratio,
            "note": "No jump over the threshold." if not jumps else
                    f"{len(jumps)} jumps over {ratio:.0%} from one frame to the next."}


def _attribute_numbers(geometry, name):
    """Mean, min and max of a point or prim attribute, by component."""
    for kind, find, read in (
            ("point", geometry.findPointAttrib, geometry.pointFloatAttribValues),
            ("prim", geometry.findPrimAttrib, geometry.primFloatAttribValues)):
        attribute = find(name)
        if attribute is None:
            continue
        if attribute.dataType() == hou.attribData.Int:
            read = geometry.pointIntAttribValues if kind == "point" else geometry.primIntAttribValues
        elif attribute.dataType() != hou.attribData.Float:
            return {"class": kind, "note": "not a number"}
        values = np.array(read(name), dtype=float).reshape(-1, attribute.size())
        if not len(values):
            return {"class": kind, "mean": None}
        return {"class": kind, "mean": _round(values.mean(0)), "min": _round(values.min(0)),
                "max": _round(values.max(0))}
    return {"mean": None, "note": "no point or prim attribute of this name"}
