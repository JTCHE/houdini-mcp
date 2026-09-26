"""USD/Solaris (LOP) handlers."""
import hou


def lop_stage_info(path):
    """Get USD stage info from a LOP node: prims, layers, time codes."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    stage = node.stage()
    if not stage:
        raise ValueError(f"No USD stage on: {path}")
    root_prims = [str(p.GetPath()) for p in stage.GetPseudoRoot().GetChildren()]
    default_prim = str(stage.GetDefaultPrim().GetPath()) if stage.HasDefaultPrim() else None
    return {
        "path": node.path(),
        "prim_count": len(list(stage.Traverse())),
        "root_prims": root_prims,
        "default_prim": default_prim,
        "layer_count": len(stage.GetLayerStack()),
        "start_time": stage.GetStartTimeCode(),
        "end_time": stage.GetEndTimeCode(),
    }


def lop_prim_get(path, prim_path, include_attrs=False):
    """Get details of a specific USD prim."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    stage = node.stage()
    if not stage:
        raise ValueError(f"No USD stage on: {path}")
    prim = stage.GetPrimAtPath(prim_path)
    if not prim:
        raise ValueError(f"Prim not found: {prim_path}")
    info = {
        "prim_path": str(prim.GetPath()),
        "type": str(prim.GetTypeName()),
        "children": [str(c.GetPath()) for c in prim.GetChildren()],
    }
    if include_attrs:
        attrs = {}
        for attr in prim.GetAttributes():
            val = attr.Get()
            attrs[attr.GetName()] = str(val) if val is not None else None
        info["attributes"] = attrs
    return info


def lop_prim_search(path, pattern, type_name=None):
    """Search for USD prims matching a pattern."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    rule = hou.LopSelectionRule()
    rule.setPathPattern(pattern)
    if type_name:
        rule.setTypeName(type_name)
    prims = rule.expandedPaths(node)
    return {
        "path": node.path(),
        "pattern": pattern,
        "matches": [str(p) for p in prims],
        "count": len(prims),
    }


def lop_layer_info(path):
    """Get USD layer stack info from a LOP node."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    stage = node.stage()
    if not stage:
        raise ValueError(f"No USD stage on: {path}")
    layers = []
    for layer in stage.GetLayerStack():
        layers.append({
            "identifier": layer.identifier,
            "path": layer.realPath,
        })
    return {"path": node.path(), "layers": layers, "count": len(layers)}


def list_usd_prims(path, root_prim="/", max_depth=3):
    """List USD prims up to a given depth."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    stage = node.stage()
    if not stage:
        raise ValueError(f"No USD stage on: {path}")
    prims = []

    def _walk(prim, depth):
        if depth > max_depth:
            return
        prims.append({
            "path": str(prim.GetPath()),
            "type": str(prim.GetTypeName()),
            "depth": depth,
        })
        for child in prim.GetChildren():
            _walk(child, depth + 1)

    root = stage.GetPrimAtPath(root_prim) if root_prim != "/" else stage.GetPseudoRoot()
    if not root:
        raise ValueError(f"Root prim not found: {root_prim}")
    for child in root.GetChildren():
        _walk(child, 1)
    return {"path": path, "count": len(prims), "prims": prims}


def get_usd_attribute(path, prim_path, attr_name):
    """Get a specific USD attribute value."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    stage = node.stage()
    if not stage:
        raise ValueError(f"No USD stage on: {path}")
    prim = stage.GetPrimAtPath(prim_path)
    if not prim:
        raise ValueError(f"Prim not found: {prim_path}")
    attr = prim.GetAttribute(attr_name)
    if not attr:
        raise ValueError(f"Attribute not found: {attr_name}")
    return {"prim": prim_path, "attr": attr_name, "value": str(attr.Get()), "type": str(attr.GetTypeName())}


def world_transform(path, prim_path):
    """Where a prim is in the world at the current frame: the composed
    transform of the prim and every parent, not the local xformOps."""
    from pxr import Usd, UsdGeom
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    prim = node.stage().GetPrimAtPath(prim_path)
    if not prim:
        raise ValueError(f"Prim not found: {prim_path}")
    if not prim.IsA(UsdGeom.Xformable):
        raise ValueError(f"{prim_path} is a {prim.GetTypeName() or 'typeless'} prim, and it "
                         f"has no transform.")
    matrix = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode(hou.frame()))
    # USD and Houdini both store a row-major matrix with the translation last.
    parts = hou.Matrix4([list(row) for row in matrix]).explode()
    return {"prim": prim_path,
            "translate": [round(value, 6) for value in parts["translate"]],
            "rotate": [round(value, 6) for value in parts["rotate"]],
            "scale": [round(value, 6) for value in parts["scale"]]}


def set_usd_attribute(path, prim_path, attr_name, value):
    """Set a USD attribute value."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    stage = node.stage()
    if not stage:
        raise ValueError(f"No USD stage on: {path}")
    prim = stage.GetPrimAtPath(prim_path)
    if not prim:
        raise ValueError(f"Prim not found: {prim_path}")
    attr = prim.GetAttribute(attr_name)
    if not attr:
        raise ValueError(f"Attribute not found: {attr_name}")
    attr.Set(value)
    return {"prim": prim_path, "attr": attr_name, "set": True}


def get_usd_prim_stats(path, prim_path):
    """Get stats about a USD prim: child count, attr count, etc."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    stage = node.stage()
    if not stage:
        raise ValueError(f"No USD stage on: {path}")
    prim = stage.GetPrimAtPath(prim_path)
    if not prim:
        raise ValueError(f"Prim not found: {prim_path}")
    return {
        "prim": prim_path,
        "type": str(prim.GetTypeName()),
        "child_count": len(prim.GetChildren()),
        "attr_count": len(prim.GetAttributes()),
        "is_active": prim.IsActive(),
        "has_payload": prim.HasPayload(),
    }


def get_last_modified_prims(path, count=10):
    """Get recently modified prims from the edit target layer."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    stage = node.stage()
    if not stage:
        raise ValueError(f"No USD stage on: {path}")
    edit_layer = stage.GetEditTarget().GetLayer()
    prims = []
    for prim_path in edit_layer.rootPrims:
        prims.append(str(prim_path))
        if len(prims) >= count:
            break
    return {"path": path, "prims": prims}


def create_lop_node(parent_path, node_type, name=None):
    """Create a LOP node."""
    parent = hou.node(parent_path)
    if not parent:
        raise ValueError(f"Parent not found: {parent_path}")
    node = parent.createNode(node_type, node_name=name)
    return {"path": node.path(), "name": node.name(), "type": node_type}


def get_usd_composition(path, prim_path):
    """Get composition arcs (references, payloads, inherits, etc.) for a prim."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    stage = node.stage()
    if not stage:
        raise ValueError(f"No USD stage on: {path}")
    prim = stage.GetPrimAtPath(prim_path)
    if not prim:
        raise ValueError(f"Prim not found: {prim_path}")
    arcs = {
        "references": bool(prim.GetReferences()),
        "payloads": bool(prim.GetPayloads()),
        "inherits": bool(prim.GetInherits()),
        "specializes": bool(prim.GetSpecializes()),
    }
    return {"prim": prim_path, "composition": arcs}


def get_usd_variants(path, prim_path):
    """Get variant sets and selections for a prim."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    stage = node.stage()
    if not stage:
        raise ValueError(f"No USD stage on: {path}")
    prim = stage.GetPrimAtPath(prim_path)
    if not prim:
        raise ValueError(f"Prim not found: {prim_path}")
    variant_sets = {}
    for vs_name in prim.GetVariantSets().GetNames():
        vs = prim.GetVariantSet(vs_name)
        variant_sets[vs_name] = {
            "choices": vs.GetVariantNames(),
            "selection": vs.GetVariantSelection(),
        }
    return {"prim": prim_path, "variant_sets": variant_sets}


def inspect_usd_layer(path, layer_index=0):
    """Inspect a specific USD layer by index in the stack."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    stage = node.stage()
    if not stage:
        raise ValueError(f"No USD stage on: {path}")
    layers = stage.GetLayerStack()
    if layer_index >= len(layers):
        raise ValueError(f"Layer index {layer_index} out of range (max {len(layers) - 1})")
    layer = layers[layer_index]
    return {
        "index": layer_index,
        "identifier": layer.identifier,
        "path": layer.realPath,
        "root_prims": [str(p) for p in layer.rootPrims],
    }


def list_lights(path):
    """List all light prims in a USD stage."""
    node = hou.node(path)
    if not node:
        raise ValueError(f"Node not found: {path}")
    stage = node.stage()
    if not stage:
        raise ValueError(f"No USD stage on: {path}")
    lights = []
    for prim in stage.Traverse():
        type_name = str(prim.GetTypeName())
        if "Light" in type_name:
            lights.append({
                "path": str(prim.GetPath()),
                "type": type_name,
            })
    return {"path": path, "count": len(lights), "lights": lights}


def lop_import(path, file, method="reference", prim_path=None):
    """Import a USD file via reference or sublayer."""
    parent = hou.node(path)
    if not parent:
        raise ValueError(f"Parent path not found: {path}")
    if method == "reference":
        node = parent.createNode("reference", "usd_import")
        node.parm("filepath1").set(file)
        if prim_path:
            node.parm("primpath").set(prim_path)
    elif method == "sublayer":
        node = parent.createNode("sublayer", "usd_import")
        node.parm("filepath1").set(file)
    else:
        raise ValueError(f"Unknown import method: {method}")
    return {"imported": True, "path": node.path(), "file": file, "method": method}
