"""The .hip file: save it, load one, read what is open, or step its undo history."""
import hou

from . import unknown_mode
from ..handlers import scene

MODES = ("info", "save", "load", "undo", "redo", "merge", "list_file")


def MUTATES(params):
    # An undo inside an undo group would undo the group itself.
    return params.get("mode") in ("save", "load", "merge")


def run(mode="info", path=None, count=1, nodes=None):
    if mode == "info":
        return {**scene.get_scene_info(),
                "unsaved_changes": hou.hipFile.hasUnsavedChanges()}
    if mode == "save":
        return scene.save_scene(path)
    if mode == "load":
        if not path:
            raise ValueError("mode 'load' needs the path of a .hip file.")
        return scene.load_scene(path)
    if mode == "merge":
        if not path or not nodes:
            raise ValueError("mode 'merge' needs path, the .hip file, and nodes, the node "
                             "paths to bring. Read them with mode 'list_file'.")
        return scene.merge_file(path, nodes)
    if mode == "list_file":
        if not path:
            raise ValueError("mode 'list_file' needs path, the .hip file.")
        return scene.list_file(path, nodes)
    if mode in ("undo", "redo"):
        return _step(mode, count)
    raise unknown_mode(mode, MODES)


def _step(mode, count):
    labels = hou.undos.undoLabels if mode == "undo" else hou.undos.redoLabels
    perform = hou.undos.performUndo if mode == "undo" else hou.undos.performRedo
    done = []
    for _ in range(max(1, count)):
        if not labels():
            break
        done.append(labels()[0])
        perform()
    report = {"undone" if mode == "undo" else "redone": done,
              "next_undo": list(hou.undos.undoLabels()[:5]),
              "next_redo": list(hou.undos.redoLabels()[:5])}
    if len(done) < count:
        report["note"] = f"The history held only {len(done)} step(s) to {mode}."
    return report
