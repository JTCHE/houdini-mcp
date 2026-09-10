"""docs — the official Houdini documentation."""
import json

from ..connection import call


def tool(query: str = None, page: str = None, node: str = None,
         category: str = None, limit: int = 5) -> str:
    """Read the official Houdini documentation.

    This is the authority on every node, parameter, VEX function and HOM call.
    Read the page before you use an API that you have not confirmed in this
    session: names and enum members change between Houdini releases, and a
    wrong one often fails without a message.

    Do not answer from memory, and do not read sidefx.com yourself.

    Give exactly one of:
        query — words to search, for example "copy to points". Returns the
                hits with their page paths. Read one with `page`.
        page  — a page path from a hit, for example
                "houdini/nodes/sop/copytopoints". A loose name or a sidefx.com
                address also works. Returns the text of the page.
        node  — a path to a node in the scene, for example
                "/obj/geo1/attribwrangle1". Returns the page of that node type.
                This is the only mode that needs Houdini.

    category: keep the search inside one category, for example
    "Nodes > Geometry nodes", "VEX > VEX Functions" or "Python scripting > hou".

    Returns markdown for a page, JSON for a search.
    """
    import houdini_docs

    given = [name for name, value in
             (("query", query), ("page", page), ("node", node)) if value]
    if len(given) != 1:
        return "Give exactly one of query, page or node."

    if query:
        results = houdini_docs.search(query, limit, category)
        if isinstance(results, dict):
            return f"Error: {results['error']}"
        return json.dumps(results, indent=2)

    if node:
        meta = call("docs", {"node": node})
        page = houdini_docs.node_page(meta.get("type_name", ""),
                                      meta.get("category", ""),
                                      meta.get("default_help_url"))
        result = houdini_docs.get_page(page)
        if "error" in result:
            # An asset can carry a help address that has no page. Use its name.
            result = houdini_docs.get_page(
                houdini_docs.type_base_name(meta.get("type_name", "")))
        if "content" in result:
            return result["content"]
        return f"Error: {result['error']} ({page})"

    result = houdini_docs.get_page(page)
    if "error" in result:
        return f"Error: {result['error']} ({result['page']})"
    return result["content"]
