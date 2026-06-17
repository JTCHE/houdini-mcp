"""VEX wrangle creation and validation handlers."""
import hou


def create_wrangle(parent_path, wrangle_type="attribwrangle", name=None, code=""):
    """Create a VEX wrangle node with optional initial code."""
    parent = hou.node(parent_path)
    if not parent:
        raise ValueError(f"Parent not found: {parent_path}")
    node = parent.createNode(wrangle_type, node_name=name)
    if code:
        snippet_parm = node.parm("snippet")
        if snippet_parm:
            snippet_parm.set(code)
    return {"path": node.path(), "name": node.name(), "type": wrangle_type}


def set_wrangle_code(node_path, code):
    """Set the VEX code on a wrangle node."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parm = node.parm("snippet")
    if not parm:
        raise ValueError(f"Node {node_path} has no 'snippet' parameter")
    parm.set(code)
    return {"path": node_path, "code_length": len(code)}


def get_wrangle_code(node_path):
    """Get the VEX code from a wrangle node."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    parm = node.parm("snippet")
    if not parm:
        raise ValueError(f"Node {node_path} has no 'snippet' parameter")
    return {"path": node_path, "code": parm.eval()}


def create_vex_expression(parent_path, attrib_name, expression, run_over="Points"):
    """Create a wrangle node that evaluates a VEX expression and stores it in an attribute."""
    parent = hou.node(parent_path)
    if not parent:
        raise ValueError(f"Parent not found: {parent_path}")
    code = f'@{attrib_name} = {expression};'
    node = parent.createNode("attribwrangle", node_name=f"expr_{attrib_name}")
    node.parm("snippet").set(code)
    class_parm = node.parm("class")
    if class_parm:
        run_over_map = {"Detail": 0, "Points": 1, "Vertices": 2, "Primitives": 3}
        val = run_over_map.get(run_over, 1)
        class_parm.set(val)
    return {"path": node.path(), "attrib": attrib_name, "code": code}


def validate_vex(code):
    """Validate VEX by compiling it in a throwaway wrangle and reading cook errors.

    HOM has no direct VEX-string syntax checker, so we cook a temporary
    attribwrangle (fed one point) and report any compile/cook errors.
    """
    tmp = hou.node("/obj").createNode("geo", node_name="__vex_validate_tmp")
    try:
        add = tmp.createNode("add")
        add.parm("points").set(1)
        wr = tmp.createNode("attribwrangle")
        wr.parm("snippet").set(code)
        wr.setInput(0, add)
        try:
            wr.cook(force=True)
        except hou.OperationFailed:
            pass  # cook errors are captured via wr.errors() below
        errors = list(wr.errors())
        return {"valid": len(errors) == 0, "errors": errors or None}
    finally:
        tmp.destroy()
