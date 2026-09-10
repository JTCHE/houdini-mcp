"""docs — the official Houdini documentation."""
import json
import re

from ..connection import call

# hou node category name -> documentation folder, where the two differ.
CATEGORY_TO_DIR = {
    "Object": "obj",
    "Driver": "out",
    "Manager": "mgr",
    "CopNet": "cop2",
    "VopNet": "vop",
    "Shop": "shop",
}


def tool(query: str = None, page: str = None, node: str = None,
         category: str = None, limit: int = 5, build: str = None) -> str:
    """Read the official Houdini documentation.

    This is the authority on every node, parameter, VEX function and HOM call.
    Read the page before you use an API that you have not confirmed in this
    session: names and enum members change between Houdini releases, and a
    wrong one often fails without a message.

    Do not answer from memory, and do not read sidefx.com yourself.

    The pages come from the Houdini install on this machine, so they match the
    build exactly. The first search on a build indexes it, which takes about
    twenty seconds. A page read never waits for the index.

    Give exactly one of:
        query — words to search, for example "copy to points". Returns the
                hits with their page paths. Read one with `page`.
        page  — a page path from a hit, for example "nodes/sop/copytopoints".
                A loose name or a sidefx.com address also works. Returns the
                text of the page.
        node  — a path to a node in the scene, for example
                "/obj/geo1/attribwrangle1". Returns the page of that node type.
                This is the only mode that needs Houdini.

    category: keep the search inside one folder of pages, for example
    "nodes/sop", "vex/functions" or "hom/hou".

    build: read a specific Houdini build, for example "21.0.829". Default: the
    Houdini in $HFS, then the newest build on this machine.

    Returns markdown for a page, JSON for a search.
    """
    try:
        import houdinimd_docs
    except ImportError:
        return "Error: the documentation engine is not installed. Run: uv pip install houdinimd-docs"

    given = [name for name, value in
             (("query", query), ("page", page), ("node", node)) if value]
    if len(given) != 1:
        return "Give exactly one of query, page or node."

    try:
        if query:
            return json.dumps(search(houdinimd_docs, query, limit, category, build), indent=2)
        if node:
            meta = call("docs", {"node": node})
            path = node_page(meta.get("type_name", ""), meta.get("category", ""),
                             meta.get("default_help_url"))
            try:
                return read(houdinimd_docs, path, build)
            except ValueError:
                # An asset can carry a help address that has no page. Use its name.
                return read(houdinimd_docs, type_base_name(meta.get("type_name", "")), build)
        return read(houdinimd_docs, page, build)
    except (ValueError, RuntimeError) as error:
        return f"Error: {error}"


def search(engine, query, limit, category, build):
    # ponytail: the category is a filter after the ranking, so a narrow folder
    # needs the wide fetch. Push it into the SQL if a filter comes back short.
    wanted = max(limit * 40, 200) if category else limit
    hits = json.loads(engine.search(query, wanted, build))
    if category:
        prefix = category.strip("/") + "/"
        hits = [hit for hit in hits if hit["path"].startswith(prefix)][:limit]
    return [
        {
            "path": hit["path"],
            "title": hit["title"],
            "type": hit.get("nodeType"),
            "summary": hit.get("summary"),
            "sections": [section["heading"] for section in hit["headings"] if section["heading"]],
            "score": round(hit["score"], 2),
        }
        for hit in hits
    ]


def read(engine, reference, build):
    """The page as markdown. A reference with no path in it is a name, and the
    best search hit for that name is the page."""
    path = normalize_page(reference)
    try:
        view = json.loads(engine.page(path, build))
    except ValueError:
        if "/" in path:
            raise
        hits = json.loads(engine.search(reference, 1, build))
        if not hits:
            raise
        view = json.loads(engine.page(hits[0]["path"], build))
    head = [f"# {view['name']}"]
    if view.get("nodeType"):
        head.append(f"*{view['nodeType']}*")
    if view.get("summary"):
        head.append(view["summary"])
    head.append(f"Page `{view['path']}`, Houdini {view['version']}.")
    return "\n\n".join(head) + "\n\n" + view["markdown"]


def normalize_page(reference: str) -> str:
    """Turn any reference to a documentation page into a page path.

    Accepts a page path, a HoudiniMD or SideFX address, and a trailing .md or
    .html: "https://www.sidefx.com/docs/houdini/nodes/sop/box.html" is
    "nodes/sop/box".
    """
    page = re.sub(r"^https?://[^/]+/", "", reference.strip())
    page = re.sub(r"^(docs|api/raw)/", "", page.strip("/"))
    page = re.sub(r"\.(md|html)$", "", page).strip("/")
    return re.sub(r"^houdini/", "", page)


def type_base_name(type_name: str) -> str:
    """Strip the namespace and version: 'labs::attribwrangle::2.0' -> 'attribwrangle'."""
    return re.sub(r"::\d+(\.\d+)*$", "", type_name).split("::")[-1].strip("_")


def node_page(type_name: str, category: str, help_url: str = None) -> str:
    """The page path for a node type.

    The node type's own help URL wins ('operator:Sop/attribwrangle'). Without
    one, the page is built from the type name and category, with the namespace
    and version stripped: ('labs::attribwrangle::2.0', 'Sop') -> the plain
    attribwrangle page.
    """
    if help_url:
        match = re.match(r"operator:([^/]+)/(.+)", help_url)
        if match:
            category, type_name = match.group(1), match.group(2)
        elif "://" in help_url:
            return normalize_page(help_url)
    folder = CATEGORY_TO_DIR.get(category, category.lower())
    return f"nodes/{folder}/{type_base_name(type_name)}"
