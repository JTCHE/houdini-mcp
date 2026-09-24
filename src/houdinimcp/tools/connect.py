"""Wire nodes together, break a wire, or change input order."""
from . import items_of, unknown_mode
from ..handlers import nodes

MUTATES = True

MODES = ("connect", "disconnect", "reorder")


def run(items=None, mode="connect", **defaults):
    wires = items_of(mode, items, defaults)
    if mode == "connect":
        return nodes.connect_nodes_batch([
            {"src_path": wire["src_path"], "dst_path": wire["dst_path"],
             "dst_input_index": wire.get("dst_input_index", 0),
             "src_output_index": wire.get("src_output_index", 0)}
            for wire in wires])
    if mode == "disconnect":
        return [nodes.disconnect_node_input(wire["path"], wire.get("input_index", 0))
                for wire in wires]
    if mode == "reorder":
        return nodes.reorder_inputs(wires[0]["path"], wires[0]["input_indices"])
    raise unknown_mode(mode, MODES)
