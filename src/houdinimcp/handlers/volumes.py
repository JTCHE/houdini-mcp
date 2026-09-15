"""Volumes and VDBs: measure them, read them, and sample them at positions.

`hou.Volume` and `hou.VDB` do not share their method names, so a script that
works on one fails on the other. Every function here takes both.

Sampling runs in VEX through a verb, never in a Python loop: a loop over
160,000 voxels takes seconds and holds the whole Houdini session while it runs.
"""
import hou

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


def stats(node_path, name=None, frame=None, bins=0):
    """The numbers that say what a volume holds, without a picture.

    Mean, the extremes, the share of voxels over a threshold and the detail
    (the mean gradient over the mean value) answer most questions about a
    simulation, and they cost one call.
    """
    node, geo = geometry.resolve(node_path, frame)
    found = []
    for prim in _named(geo, name):
        report = describe(prim, geo)
        values, shape, _origin = read_voxels(prim)
        numbers = sorted(values)
        count = len(numbers)
        if count:
            report["voxel_count"] = count
            report["shape"] = shape
            report["percentiles"] = {
                str(share): numbers[min(count - 1, int(count * share / 100))]
                for share in (1, 25, 50, 75, 99)
            }
            above_zero = sum(1 for value in numbers if value > 0)
            report["share_above_zero"] = round(above_zero / count, 4)
        if bins:
            report["histogram"] = _histogram(numbers, bins)
        found.append(report)
    return {"path": node_path, "count": len(found), "volumes": found}


def _histogram(sorted_values, bins):
    """How many voxels fall in each band between the lowest and the highest."""
    if not sorted_values:
        return []
    low, high = sorted_values[0], sorted_values[-1]
    width = (high - low) / bins or 1.0
    counts = [0] * bins
    for value in sorted_values:
        index = min(bins - 1, int((value - low) / width))
        counts[index] += 1
    return [{"from": low + width * index, "to": low + width * (index + 1),
             "voxels": counts[index]} for index in range(bins)]


def voxels(node_path, name, frame=None, limit=20000):
    """One volume as a flat array of numbers, with its shape and its transform.

    The array is what a caller needs to measure a field itself. It is cut at
    `limit` numbers, because a full simulation grid is far more than a client
    can hold; the shape says how many there really are.
    """
    node, geo = geometry.resolve(node_path, frame)
    prim = _named(geo, name)[0]
    values, shape, origin = read_voxels(prim)
    report = {**describe(prim, geo), "shape": shape, "index_origin": origin,
              "voxel_count": len(values),
              "transform": [list(row) for row in prim.transform().asTuple()]
              if hasattr(prim.transform(), "asTuple") else str(prim.transform())}
    report["values"] = list(values[:limit])
    if len(values) > limit:
        report["note"] = (f"{len(values)} voxels, and the first {limit} are here. Use mode "
                          f"'volume_stats' for the numbers, or 'volume_sample' for the "
                          f"values at the places that matter.")
    return report


def sample(node_path, names, positions=None, from_node=None, frame=None, limit=5000):
    """Read named volumes at a list of world positions.

    `positions` is a list of [x, y, z]. `from_node` takes the points of another
    node as the positions instead, so "what does the collision field read where
    there is smoke" is one call.

    `limit` holds the number of positions down. Each read is one call into
    Houdini, and a read of a whole grid would hold the session for seconds.
    """
    node, geo = geometry.resolve(node_path, frame)
    names = [names] if isinstance(names, str) else list(names)
    have = geometry.volume_names(geo)
    missing = [name for name in names if name not in have]
    if missing:
        raise ValueError(f"No volume named {', '.join(missing)}. This geometry has: "
                         f"{', '.join(have) or 'no volumes'}.")

    if from_node:
        _other, other_geo = geometry.resolve(from_node, frame)
        places = [list(point.position()) for point in other_geo.points()[:limit]]
    elif positions:
        places = [list(position) for position in positions]
    else:
        raise ValueError("Give positions, a list of [x, y, z], or from_node, a node whose "
                         "points are the positions.")
    cut = len(places) > limit
    places = places[:limit]
    values = _read_at(geo, names, places)

    report = {"path": node_path, "positions": len(places), "values": values}
    report["summary"] = {
        name: ({"min": min(numbers), "max": max(numbers),
                "mean": sum(numbers) / len(numbers)} if numbers else None)
        for name, numbers in values.items()
    }
    if cut:
        report["note"] = (f"Only the first {limit} positions were read. Raise `limit` if "
                          f"you need more, and know that each read holds the session.")
    return report


def _read_at(geo, names, places):
    """The value of each named field at each position."""
    fields = {name: _named(geo, name)[0] for name in names}
    return {name: [float(prim.sample(hou.Vector3(place))) for place in places]
            for name, prim in fields.items()}


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
    places = _grid_places(field)
    read = _read_at(geo, [name, against], places)
    here, there = read[name], read[against]
    if not here:
        return {"path": node_path, "field": name, "against": against, "samples": 0}

    low, high = min(there), max(there)
    width = (high - low) / bands or 1.0
    totals = [0.0] * bands
    counts = [0] * bands
    for value, band_value in zip(here, there):
        index = min(bands - 1, int((band_value - low) / width))
        totals[index] += value
        counts[index] += 1
    return {
        "path": node_path, "field": name, "against": against,
        "samples": len(here),
        "total_of_field": sum(here),
        "bands": [{"from": low + width * index, "to": low + width * (index + 1),
                   "samples": counts[index], "total": totals[index]}
                  for index in range(bands)],
    }
