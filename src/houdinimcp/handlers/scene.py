"""Scene management handlers."""
import os
import traceback

import hou


def get_asset_lib_status():
    """Checks if the user toggled asset library usage in hou.session."""
    use_assetlib = getattr(hou.session, "houdinimcp_use_assetlib", False)
    msg = ("Asset library usage is enabled."
           if use_assetlib
           else "Asset library usage is disabled.")
    return {"enabled": use_assetlib, "message": msg}


def get_scene_info():
    """Returns basic info about the current .hip file and a few top-level nodes."""
    try:
        hip_file = hou.hipFile.name()
        scene_info = {
            "name": os.path.basename(hip_file) if hip_file else "Untitled",
            "filepath": hip_file or "",
            "node_count": len(hou.node("/").allSubChildren()),
            "nodes": [],
            "fps": hou.fps(),
            "start_frame": hou.playbar.frameRange()[0],
            "end_frame": hou.playbar.frameRange()[1],
        }

        root = hou.node("/")
        contexts = ["obj", "shop", "out", "ch", "vex", "stage"]
        top_nodes = []

        for ctx_name in contexts:
            ctx_node = root.node(ctx_name)
            if ctx_node:
                children = ctx_node.children()
                for node in children:
                    if len(top_nodes) >= 10:
                        break
                    top_nodes.append({
                        "name": node.name(),
                        "path": node.path(),
                        "type": node.type().name(),
                        "category": ctx_name,
                    })
                if len(top_nodes) >= 10:
                    break

        scene_info["nodes"] = top_nodes
        return scene_info

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}


def save_scene(file_path=None):
    """Save the current scene, optionally to a new path."""
    if file_path:
        hou.hipFile.save(file_path)
    else:
        hou.hipFile.save()
    return {"saved": True, "file": hou.hipFile.name()}


def load_scene(file_path):
    """Load a .hip file."""
    hou.hipFile.load(file_path)
    return {"loaded": True, "file": hou.hipFile.name()}


def set_frame(frame):
    """Set the current frame in Houdini's playbar."""
    hou.setFrame(frame)
    # Read back: a frame that did not change must not pass for one that did.
    return {"frame": hou.frame()}


# The depth of the node pattern of a merge. hou.hipFile.merge brings a node
# without its children unless the pattern names them too.
MERGE_DEPTH = 12

LIST_SCRIPT = r'''
import json, sys, hou
hou.hipFile.load(sys.argv[1], suppress_save_prompt=True, ignore_load_warnings=True)
roots = sys.argv[2:] or [child.path() for child in hou.node("/").children()]
found = []
for root in roots:
    node = hou.node(root)
    for one in ([node] + list(node.children())) if node else []:
        found.append({"path": one.path(), "type": one.type().name(),
                      "children": len(one.children()),
                      "inputs": [i.path() if i else None for i in one.inputs()]})
print("MCPLIST" + json.dumps(found))
'''


def list_file(file_path, nodes=None):
    """The nodes of another .hip file, read by a separate hython, so the
    session that answers loads nothing. `nodes` are the networks to list;
    without them, the top networks."""
    import json
    import subprocess
    import sys
    if not os.path.isfile(file_path):
        raise ValueError(f"There is no file at {file_path}.")
    hython = os.path.join(hou.getenv("HFS"), "bin",
                          "hython.exe" if sys.platform == "win32" else "hython")
    done = subprocess.run([hython, "-c", LIST_SCRIPT, file_path, *(nodes or ())],
                          capture_output=True, text=True, timeout=600)
    marker = next((line for line in done.stdout.splitlines() if line.startswith("MCPLIST")), None)
    if marker is None:
        raise ValueError(f"hython could not read {file_path}: {done.stderr[-800:]}")
    return {"file": file_path, "nodes": json.loads(marker[len("MCPLIST"):])}


def merge_file(file_path, nodes):
    """Merge `nodes` of another .hip file into this session, each with all its
    children and the wires inside, and report what it made."""
    if not os.path.isfile(file_path):
        raise ValueError(f"There is no file at {file_path}.")
    pattern = " ".join(f"{path.rstrip('/')}{'/*' * depth}"
                       for path in nodes for depth in range(MERGE_DEPTH))
    conflicts = [node.path() for node in hou.hipFile.collisionNodesIfMerged(file_path, pattern)]
    before = {node.path() for node in hou.node("/").allSubChildren()}
    hou.hipFile.merge(file_path, node_pattern=pattern, ignore_load_warnings=True)
    made = sorted(node.path() for node in hou.node("/").allSubChildren()
                  if node.path() not in before)
    top = [path for path in made if not any(path.startswith(other + "/") for other in made)]
    report = {"file": file_path, "made": top, "node_count": len(made)}
    if conflicts:
        report["renamed"] = (f"These names were in use, so Houdini renamed the merged "
                             f"nodes: {', '.join(conflicts)}. Use the paths in `made`.")
    if not made:
        report["note"] = ("Nothing was merged: no node of the file matches these paths. "
                          "Read the paths with mode 'list_file'.")
    return report
