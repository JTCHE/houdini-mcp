"""Read or set the node selection."""
from . import as_list
from ..handlers import context

MUTATES = True


def run(paths=None):
    """No paths reads the selection. Paths set it."""
    if paths is None:
        return context.get_selection()
    return context.set_selection(as_list(paths))
