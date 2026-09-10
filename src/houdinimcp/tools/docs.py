"""The Houdini side of the docs tool: which page belongs to a node in the scene."""
from ..handlers import nodes

MUTATES = False


def run(node):
    return nodes.get_node_doc_meta(node)
