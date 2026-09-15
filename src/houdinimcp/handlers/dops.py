"""DOP (dynamics/simulation) handlers."""
import hou


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
    """Throw away the cache of a simulation, so that the next cook runs it again.

    A solver keeps its result in memory. After a change inside it, the node
    gives the old result back, with no error and no warning, and the change
    looks as if it did nothing. This presses the Reset Simulation button of the
    node and of every DOP network inside it, which is where a solver SOP such
    as a Pyro, FLIP, Vellum or RBD solver keeps the simulation.
    """
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")

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
        raise ValueError(f"{path} has no Reset Simulation button, and neither has any node "
                         f"inside it. A solver SOP, a DOP network or a node above one of "
                         f"them can be reset.")
    return {"path": path, "pressed": pressed,
            "note": "The next cook runs the simulation again from its start frame."}


def get_sim_memory_usage(path):
    """Get memory usage of a simulation."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    dop = node.simulation()
    if not dop:
        raise ValueError(f"No simulation on: {path}")
    return {"path": path, "memory_bytes": dop.memoryUsage()}
