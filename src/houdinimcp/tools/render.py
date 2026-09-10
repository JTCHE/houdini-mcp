"""Render nodes: make one, read or start it, and follow its progress."""
from . import unknown_mode
from ..handlers import rendering

MUTATES = True

MODES = ("start", "progress", "settings", "create")


def run(path=None, mode="start", frame_range=None, render_type="opengl", name=None,
        parent_path="/out"):
    if mode == "start":
        return rendering.start_render(path, frame_range)
    if mode == "progress":
        return rendering.get_render_progress(path)
    if mode == "settings":
        return rendering.get_render_settings(path)
    if mode == "create":
        return rendering.create_render_node(render_type, name, parent_path)
    raise unknown_mode(mode, MODES)
