"""The .hip file: save it, load one, or read what is open."""
import hou

from . import unknown_mode
from ..handlers import scene

MUTATES = True

MODES = ("info", "save", "load")


def run(mode="info", path=None):
    if mode == "info":
        return {**scene.get_scene_info(),
                "unsaved_changes": hou.hipFile.hasUnsavedChanges()}
    if mode == "save":
        return scene.save_scene(path)
    if mode == "load":
        if not path:
            raise ValueError("mode 'load' needs the path of a .hip file.")
        return scene.load_scene(path)
    raise unknown_mode(mode, MODES)
