"""DOP (dynamics/simulation) handlers."""
import hou

from . import timing


def get_simulation_info(path):
    """Get simulation info from a DOP network."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    dop = node.simulation()
    if not dop:
        raise ValueError(f"No simulation on: {path}")
    return {
        "path": node.path(),
        "memory": dop.memoryUsage(),
        "time": dop.time(),
        "objects": len(dop.objects()),
    }


def list_dop_objects(path):
    """List all DOP objects in a simulation."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    dop = node.simulation()
    if not dop:
        raise ValueError(f"No simulation on: {path}")
    objects = []
    for obj in dop.objects():
        objects.append({
            "name": obj.name(),
            "type": obj.objectType().name() if obj.objectType() else "unknown",
        })
    return {"path": path, "count": len(objects), "objects": objects}


def get_dop_object(path, object_name):
    """Get info about a specific DOP object."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    dop = node.simulation()
    if not dop:
        raise ValueError(f"No simulation on: {path}")
    obj = dop.findObject(object_name)
    if not obj:
        raise ValueError(f"DOP object not found: {object_name}")
    records = {}
    for rec in obj.records():
        records[rec.recordType()] = {f.name(): str(f.value()) for f in rec.fields()}
    return {"name": obj.name(), "records": records}


def get_dop_field(path, object_name, field_name):
    """Get a specific field from a DOP object."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    dop = node.simulation()
    if not dop:
        raise ValueError(f"No simulation on: {path}")
    obj = dop.findObject(object_name)
    if not obj:
        raise ValueError(f"DOP object not found: {object_name}")
    for rec in obj.records():
        field = rec.field(field_name)
        if field is not None:
            return {"object": object_name, "field": field_name, "value": str(field.value())}
    raise ValueError(f"Field not found: {field_name}")


def get_dop_relationships(path, object_name):
    """Get relationships of a DOP object."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    dop = node.simulation()
    if not dop:
        raise ValueError(f"No simulation on: {path}")
    obj = dop.findObject(object_name)
    if not obj:
        raise ValueError(f"DOP object not found: {object_name}")
    rels = []
    for rel in obj.relationships():
        rels.append({
            "name": rel.name(),
            "type": rel.objectType().name() if rel.objectType() else "unknown",
        })
    return {"object": object_name, "relationships": rels}


def step_simulation(path, num_steps=1):
    """Step the simulation forward by a number of frames."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    start_frame = hou.intFrame()
    for _ in range(num_steps):
        hou.setFrame(hou.intFrame() + 1)
    return {"path": path, "start_frame": start_frame, "end_frame": hou.intFrame(), "steps": num_steps}


def reset_simulation(path):
    """Throw away the cache of a simulation, and run its first frame again.

    A solver keeps its result in memory. After a change inside it, the node
    gives the old result back, with no error and no warning, and the change
    looks as if it did nothing. This presses the Reset Simulation button of the
    node and of every DOP network inside it, which is where a solver SOP such
    as a Pyro, FLIP, Vellum or RBD solver keeps the simulation.

    A reset before the source has cooked, for example just after a change of
    voxel size, starts the simulation from nothing, and every later frame
    stays empty with no error. So the order is: go to the start frame, cook
    the sources, press, cook the start frame, and press once more when the
    result is empty.
    """
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    start = _start_frame(node)
    with timing.keep_frame():
        hou.setFrame(start)
        sources = [source for source in node.inputs() if source]
        for source in sources:
            _cook(source)
        pressed = _press(node)
        report = {"path": path, "pressed": pressed, "start_frame": start}
        if not isinstance(node, hou.SopNode):
            return {**report, "note": "The next cook runs the simulation again from its "
                                      "start frame."}
        count = _cook(node)
        if count == 0:
            _press(node)
            count = _cook(node)
            report["pressed_again"] = True
        report["primitives_at_start"] = count
        source_count = sum(_cook(source) or 0 for source in sources)
        if count == 0 and source_count:
            raise ValueError(
                f"{path} is still empty at its start frame {start} after two resets, "
                f"while its sources hold {source_count} primitives. The simulation will "
                f"stay empty on every frame: do not cook or cache it. Read the errors of "
                f"the source nodes, and whether the source is written to a field that "
                f"the solver reads.")
        if count == 0:
            report["warning"] = (f"The result is empty at the start frame {start}, and so "
                                 f"are the sources. If the source begins later, this is "
                                 f"right; if not, the simulation stays empty.")
    return report


def _press(node):
    """Press every Reset Simulation button on the node and under it."""
    # Paths, not nodes: a reset rebuilds what is inside a solver SOP, and a node
    # held from before the reset is gone by the time the walk reaches it.
    paths = [node.path()] + [child.path() for child in node.allSubChildren()]
    pressed = []
    for target_path in paths:
        target = hou.node(target_path)
        if not target:
            continue
        try:
            for name in ("resimulate", "resetsimulation"):
                button = target.parm(name)
                if button:
                    button.pressButton()
                    pressed.append(f"{target_path}/{name}")
        except hou.ObjectWasDeleted:
            continue
    if not pressed:
        raise ValueError(f"{node.path()} has no Reset Simulation button, and neither has "
                         f"any node inside it. A solver SOP, a DOP network or a node above "
                         f"one of them can be reset.")
    return pressed


def _start_frame(node):
    """The frame where the simulation of the node begins."""
    for candidate in [node] + list(node.allSubChildren()):
        parm = candidate.parm("startframe")
        if parm is not None:
            return parm.eval()
    return hou.playbar.playbackRange()[0]


def _cook(node):
    """Cook a SOP at this frame and count its primitives. None for another kind
    of node, which has no geometry to count."""
    if not isinstance(node, hou.SopNode):
        return None
    try:
        node.cook(force=True)
    except hou.OperationFailed:
        pass   # the message is in node.errors()
    geometry = node.geometry()
    return geometry.intrinsicValue("primitivecount") if geometry else 0


def get_sim_memory_usage(path):
    """Get memory usage of a simulation."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    dop = node.simulation()
    if not dop:
        raise ValueError(f"No simulation on: {path}")
    return {"path": path, "memory_bytes": dop.memoryUsage()}
