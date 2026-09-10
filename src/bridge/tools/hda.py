"""hda — digital assets: what is installed, and what is inside one."""
from mcp.types import ToolAnnotations

from ..connection import call_json

ANNOTATIONS = ToolAnnotations(destructiveHint=True)


def tool(mode: str = "list", node_type: str = None, category: str = None,
         file_path: str = None, node_path: str = None, name: str = None,
         label: str = None, section_name: str = None, content: str = None) -> str:
    """Read and change Houdini digital assets.

    Use it when a node type comes from a .hda file: to find the file, to load a
    new one, or to read the scripts and the help inside it.

    Do not use it for the parameters of one node in the scene: node_inspect
    does that.

    mode:
        "list"        — the installed assets. `category` filters, for example
                        "Sop".
        "get"         — the definition of `node_type`: the file, the version
                        and the tools.
        "install"     — load the .hda file at `file_path` into the session.
        "uninstall"   — unload the .hda file at `file_path`.
        "reload"      — read the .hda file at `file_path` again, after an edit
                        on disk.
        "update"      — save the node at `node_path` back into its asset.
        "create"      — make an asset from the subnet at `node_path`, with
                        `name`, `label` and `file_path`.
        "sections"    — the section names inside `node_type`.
        "section_get" — the text of `section_name`, for example "PythonModule".
        "section_set" — write `content` into `section_name`.

    Returns JSON. "install" and "uninstall" change every node of that type in
    the session.
    """
    return call_json("hda", {"mode": mode, "node_type": node_type,
                             "category": category, "file_path": file_path,
                             "node_path": node_path, "name": name, "label": label,
                             "section_name": section_name, "content": content},
                     timeout=120.0)
