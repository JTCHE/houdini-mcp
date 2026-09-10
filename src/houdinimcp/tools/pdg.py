"""TOP networks: cook them, read their state, dirty or cancel them."""
from . import unknown_mode
from ..handlers import pdg as handler

MUTATES = True

MODES = ("cook", "status", "workitems", "dirty", "cancel")


def run(path, mode="status", state=None, dirty_all=False):
    if mode == "cook":
        return handler.pdg_cook(path)
    if mode == "status":
        return handler.pdg_status(path)
    if mode == "workitems":
        return handler.pdg_workitems(path, state)
    if mode == "dirty":
        return handler.pdg_dirty(path, dirty_all)
    if mode == "cancel":
        return handler.pdg_cancel(path)
    raise unknown_mode(mode, MODES)
