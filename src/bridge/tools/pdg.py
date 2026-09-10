"""pdg — TOP networks and their work items."""
from ..connection import call_json


def tool(path: str, mode: str = "status", state: str = None,
         dirty_all: bool = False) -> str:
    """Cook a TOP network, and read what its work items did.

    Use it for a TOP network only. A TOP node does not cook like a SOP: it
    makes work items, and each item runs on its own.

    path: the TOP network or the TOP node.

    mode:
        "status"    — the counts for each state, and whether a cook runs now.
        "workitems" — the items. `state` filters, for example "failed".
        "cook"      — start the cook. The call comes back at once; read
                      "status" after it to follow the work.
        "dirty"     — mark the node dirty. `dirty_all` also removes the
                      outputs on disk.
        "cancel"    — stop the cook that runs now.

    Returns JSON. A failed item holds the command and the log path: read those
    before you change the network.
    """
    return call_json("pdg", {"path": path, "mode": mode, "state": state,
                             "dirty_all": dirty_all}, timeout=300.0)
