"""Wire nodes together, break a wire, or change input order."""
from . import as_list, unknown_mode
from ..handlers import nodes

MUTATES = True

MODES = ("connect", "disconnect", "reorder")


def run(items=None, mode="connect", **defaults):
    if mode == "connect":
        wires = [{**defaults, **item} for item in as_list(items)] or [defaults]
        return nodes.connect_nodes_batch([
            {"src_path": wire["src_path"], "dst_path": wire["dst_path"],
             "dst_input_index": wire.get("dst_input_index", 0),
             "src_output_index": wire.get("src_output_index", 0)}
            for wire in wires])
    if mode == "disconnect":
        return [nodes.disconnect_node_input(item["path"], item.get("input_index", 0))
                for item in ([{**defaults, **i} for i in as_list(items)] or [defaults])]
    if mode == "reorder":
        return nodes.reorder_inputs(defaults["path"], defaults["input_indices"])
    raise unknown_mode(mode, MODES)
