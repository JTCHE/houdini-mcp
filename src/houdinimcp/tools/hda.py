"""Houdini digital assets: what is installed, and the sections inside one."""
from . import unknown_mode
from ..handlers import hda as handler

MUTATES = True

MODES = ("list", "get", "install", "uninstall", "reload", "update", "create",
         "sections", "section_get", "section_set")


def run(mode="list", node_type=None, category=None, file_path=None, node_path=None,
        name=None, label=None, section_name=None, content=None):
    if mode == "list":
        return handler.hda_list(category)
    if mode == "get":
        return handler.hda_get(node_type, category)
    if mode == "install":
        return handler.hda_install(file_path)
    if mode == "uninstall":
        return handler.uninstall_hda(file_path)
    if mode == "reload":
        return handler.reload_hda(file_path)
    if mode == "update":
        return handler.update_hda(node_path)
    if mode == "create":
        return handler.hda_create(node_path, name, label, file_path)
    if mode == "sections":
        return handler.get_hda_sections(node_type, category)
    if mode == "section_get":
        return handler.get_hda_section_content(node_type, section_name, category)
    if mode == "section_set":
        return handler.set_hda_section_content(node_type, section_name, content, category)
    raise unknown_mode(mode, MODES)
