"""Render nodes: make one, read or start it, and follow its progress."""
from . import unknown_mode
from ..handlers import rendering

MUTATES = True

MODES = ("start", "progress", "settings", "create", "stats", "compare")


def run(path=None, mode="start", frame_range=None, render_type="opengl", name=None,
        parent_path="/out", output_path=None, res_scale=None, wait=False, reference=None):
    if mode == "start":
        return rendering.start_render(path, frame_range, output_path, res_scale, wait)
    if mode == "progress":
        return rendering.get_render_progress(path)
    if mode == "settings":
        return rendering.get_render_settings(path)
    if mode == "create":
        return rendering.create_render_node(render_type, name, parent_path)
    if mode == "stats":
        return rendering.render_stats(output_path) or {
            "path": output_path, "note": "This image has no husk:render_stats."}
    if mode == "compare":
        return rendering.compare_images(output_path, reference)
    raise unknown_mode(mode, MODES)
