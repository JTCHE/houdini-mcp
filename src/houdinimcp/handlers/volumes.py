"""Volumes and VDBs: measure them, read them, and sample them at positions.

`hou.Volume` and `hou.VDB` do not share their method names, so a script that
works on one fails on the other. Every function here takes both.

Sampling runs in compiled code through a verb, and the numbers go through
numpy, never through a Python loop: a loop over 160,000 voxels takes seconds
and holds the whole Houdini session while it runs.
"""
import hou
import numpy

from . import geometry


def _named(geo, name=None):
    """The volume primitives of a geometry, by their `name` attribute."""
    prims = geometry.volume_primitives(geo)
    if not prims:
        return []
    named = geo.findPrimAttrib("name")
    if name is None:
        return prims
    found = [prim for prim in prims
             if named and prim.attribValue("name") == name]
    if not found:
        have = geometry.volume_names(geo)
        raise ValueError(f"No volume named '{name}'. This geometry has: "
                         f"{', '.join(have) or 'no volumes'}.")
    return found


def _voxel_size(prim):
    """The edge of one voxel. Houdini gives three numbers; a cubic voxel, which
    almost every simulation uses, makes them the same."""
    size = prim.intrinsicValue("voxelsize")
    size = list(size) if isinstance(size, (tuple, list)) else [size, size, size]
    return {"voxel_size": size[0], "voxel_size_xyz": size}


def describe(prim, geo):
    """What one volume is: name, resolution, voxel size, bounds, and its values."""
    named = geo.findPrimAttrib("name")
    bbox = prim.boundingBox()
    report = {
        "name": prim.attribValue("name") if named else "",
        "kind": type(prim).__name__,
        "resolution": list(prim.resolution()),
        "bounding_box": {"min": list(bbox.minvec()), "max": list(bbox.maxvec())},
        "is_sdf": prim.isSDF(),
        "min": prim.volumeMin(),
        "max": prim.volumeMax(),
        "mean": prim.volumeAverage(),
        **_voxel_size(prim),
    }
    if isinstance(prim, hou.VDB):
        report["active_voxels"] = prim.activeVoxelCount()
        report["vdb_type"] = prim.vdbType()
    return report


def read_voxels(prim):
    """Every voxel of a volume or a VDB as one flat tuple, with its shape.

    A VDB stores only the voxels that carry a value, so the shape is the box of
    the active region, not the resolution of the whole grid.
    """
    if isinstance(prim, hou.VDB):
        box = prim.activeVoxelBoundingBox()
        values = prim.voxelRangeAsFloat(box)
        # The box of a VDB is one wider than the array that comes back, so the
        # box is not the shape. `resolution()` is, when the count agrees.
        from_box = [int(box.maxvec()[axis] - box.minvec()[axis]) + 1 for axis in range(3)]
        origin = [int(box.minvec()[axis]) for axis in range(3)]
        shape = next((candidate for candidate in (list(prim.resolution()), from_box)
                      if candidate[0] * candidate[1] * candidate[2] == len(values)),
                     [len(values)])
    else:
        values = prim.allVoxels()
        shape = list(prim.resolution())
        origin = [0, 0, 0]
    if len(shape) != 3 or len(values) != shape[0] * shape[1] * shape[2]:
        # Say it instead of letting a caller reshape into a wrong array.
        shape = [len(values)]
        origin = None
    return values, shape, origin


def _array(prim):
    """A volume as a numpy array indexed [z, y, x], with its index origin.

    It raises when Houdini gives a count of voxels that fits no box, so a
    caller never gets an empty or a wrong array with no reason.
    """
    values, shape, origin = read_voxels(prim)
    if len(shape) != 3:
        raise ValueError(f"Houdini gave {len(values)} voxels for this volume, and that count "
                         f"fits neither its resolution {list(prim.resolution())} nor the box "
                         f"of its active voxels, so the array has no shape. Use mode "
                         f"'volume_sample' to read it at positions.")
    return numpy.asarray(values, dtype=numpy.float64).reshape(shape[2], shape[1], shape[0]), \
        shape, origin


PERCENTILES = (1, 5, 25, 50, 75, 95, 99)


def _summary(numbers, bins=0, threshold=None):
    """The numbers that describe a set of values: extremes, mean, percentiles,
    and on request a histogram and the count on each side of a threshold."""
    numbers = numpy.asarray(numbers, dtype=numpy.float64).ravel()
    if not numbers.size:
        return {"count": 0}
    report = {"count": int(numbers.size), "min": float(numbers.min()),
              "max": float(numbers.max()), "mean": float(numbers.mean()),
              "percentiles": {str(share): float(value) for share, value in
                              zip(PERCENTILES, numpy.percentile(numbers, PERCENTILES))},
              "share_above_zero": round(float((numbers > 0).mean()), 4)}
    if bins:
        counts, edges = numpy.histogram(numbers, bins=int(bins))
        report["histogram"] = [{"from": float(edges[index]), "to": float(edges[index + 1]),
                                "count": int(count)} for index, count in enumerate(counts)]
    if threshold is not None:
        below = int((numbers < threshold).sum())
        report["threshold"] = {"value": threshold, "below": below,
                               "at_or_above": int(numbers.size) - below,
                               "share_below": round(below / numbers.size, 4)}
    return report


def stats(node_path, name=None, frame=None, bins=0, threshold=None):
    """The numbers that say what a volume holds, without a picture.

    Mean, the extremes, the percentiles and the share of voxels over a
    threshold answer most questions about a simulation, and they cost one call.
    """
    node, geo = geometry.resolve(node_path, frame)
    found = []
    for prim in _named(geo, name):
        report = describe(prim, geo)
        values, shape, _origin = read_voxels(prim)
        report["shape"] = shape
        report.update(_summary(values, bins, threshold))
        found.append(report)
    return {"path": node_path, "count": len(found), "volumes": found}


AXES = {"x": 2, "y": 1, "z": 0}
REDUCTIONS = ("sum", "mean", "max", "min", "project_x", "project_y", "project_z")


def voxels(node_path, name, frame=None, limit=20000, reduce=None):
    """One volume as an array of numbers indexed [z][y][x], with its shape and
    its transform, or one reduction of it.

    A 200 by 200 by 160 field is 25 MB of numbers, and most questions need one
    number or one picture of it. `reduce` gives "sum", "mean", "max" or "min"
    of every voxel, or "project_x", "project_y" or "project_z": the sum along
    that axis, a 2D array. An array longer than `limit` numbers is thinned by
    a step that the answer names.
    """
    node, geo = geometry.resolve(node_path, frame)
    prim = _named(geo, name)[0]
    array, shape, origin = _array(prim)
    report = {**describe(prim, geo), "shape_xyz": shape, "index_origin": origin,
              "voxel_count": int(array.size),
              "transform": [list(row) for row in prim.transform().asTupleOfTuples()]}
    if reduce in ("sum", "mean", "max", "min"):
        report["reduce"] = reduce
        report["value"] = float(getattr(array, reduce)())
        return report
    if reduce:
        if reduce not in REDUCTIONS:
            raise ValueError(f"Unknown reduce '{reduce}'. Use {', '.join(REDUCTIONS)}.")
        array = array.sum(axis=AXES[reduce[-1]])
        report["reduce"] = reduce
    step = 1
    while array[tuple(slice(None, None, step) for _ in array.shape)].size > limit:
        step += 1
    if step > 1:
        array = array[tuple(slice(None, None, step) for _ in array.shape)]
        report["step"] = step
        report["note"] = (f"Every {step}th voxel on each axis, to stay under {limit} numbers. "
                          f"Raise `limit`, or use a reduction.")
    report["array_shape"] = list(array.shape)
    report["values"] = numpy.round(array, 6).tolist()
    return report


def _points(places):
    """A geometry with one point at each position."""
    points = hou.Geometry()
    points.createPoints([hou.Vector3(place) for place in places])
    return points


def _read_at(geo, names, points):
    """The value of each named field at each point of `points`, as arrays.

    The Attribute from Volume verb samples in compiled code, so a read of a
    million points costs about what a read of a hundred costs in Python.
    """
    verb = hou.sopNodeTypeCategory().nodeVerb("attribfromvolume")
    found = {}
    for name in names:
        verb.setParms({"field": name, "name": "mcp_sample", "type": 0, "size": 1})
        result = hou.Geometry()
        verb.execute(result, [points, geo])
        found[name] = numpy.asarray(result.pointFloatAttribValues("mcp_sample"))
    return found


def sample(node_path, names, positions=None, from_node=None, frame=None, limit=1000,
           bins=10, threshold=None):
    """Read named volumes at a list of world positions, or at the points of
    another node, and describe what they read.

    `from_node` answers "what does the collision field read where there is
    smoke" in one call, with no node added to the scene. The values come back
    when there are at most `limit` of them; the summary always does.
    """
    node, geo = geometry.resolve(node_path, frame)
    names = [names] if isinstance(names, str) else list(names)
    have = geometry.volume_names(geo)
    missing = [name for name in names if name not in have]
    if missing:
        raise ValueError(f"No volume named {', '.join(missing)}. This geometry has: "
                         f"{', '.join(have) or 'no volumes'}.")
    if from_node:
        _other, points = geometry.resolve(from_node, frame)
    elif positions:
        points = _points(positions)
    else:
        raise ValueError("Give positions, a list of [x, y, z], or from_node, a node whose "
                         "points are the positions.")
    read = _read_at(geo, names, points)
    count = len(points.iterPoints())
    report = {"path": node_path, "positions": count,
              "summary": {name: _summary(values, bins, threshold)
                          for name, values in read.items()}}
    if count <= limit:
        report["values"] = {name: values.tolist() for name, values in read.items()}
    else:
        report["note"] = (f"{count} positions: the summary is here, the values are not. "
                          f"Raise `limit` to get them.")
    return report


def _grid_places(prim, most=30000):
    """World positions on a regular grid over the box of a volume.

    The step grows until the count is under `most`: a simulation grid holds
    millions of voxels, each read costs a call into Houdini, and the shape of
    the answer does not change with more samples.
    """
    box = prim.boundingBox()
    size = box.sizevec()
    step = _voxel_size(prim)["voxel_size"] or 1.0
    while (size[0] / step) * (size[1] / step) * (size[2] / step) > most:
        step *= 2
    steps = [max(1, int(size[axis] / step)) for axis in range(3)]
    return [[box.minvec()[0] + (index_x + 0.5) * step,
             box.minvec()[1] + (index_y + 0.5) * step,
             box.minvec()[2] + (index_z + 0.5) * step]
            for index_x in range(steps[0])
            for index_y in range(steps[1])
            for index_z in range(steps[2])]


def compare_fields(node_path, name, against, frame=None, bands=10):
    """How much of one field sits where another field is in each band.

    The one number that answers a collision question: "how much density is
    inside the collider", where the collider is a signed distance field.
    """
    node, geo = geometry.resolve(node_path, frame)
    field = _named(geo, name)[0]
    _named(geo, against)  # confirm the second field is there before the work

    # Sample both fields on a grid in world space, over the box of the first
    # one. World space needs no voxel index, so a Volume and a VDB, which do
    # not agree on the index of a voxel, both work the same way.
    read = _read_at(geo, [name, against], _points(_grid_places(field)))
    here, there = read[name], read[against]
    if not here.size:
        return {"path": node_path, "field": name, "against": against, "samples": 0}
    counts, edges = numpy.histogram(there, bins=bands)
    totals, _edges = numpy.histogram(there, bins=edges, weights=here)
    return {
        "path": node_path, "field": name, "against": against,
        "samples": int(here.size),
        "total_of_field": float(here.sum()),
        "bands": [{"from": float(edges[index]), "to": float(edges[index + 1]),
                   "samples": int(counts[index]), "total": float(totals[index])}
                  for index in range(bands)],
    }
