"""docs — the official Houdini documentation."""
import json
import os
import re
import sys
from urllib.parse import parse_qsl

from ..connection import call

# Characters in one answer. A client drops a tool result much longer than this,
# and hou.Geometry alone is 140,000.
LIMIT = 20_000

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
         category: str = None, limit: int = 5, build: str = None,
         section: str = None, part: int = 1) -> str:
    """Read the official Houdini documentation.

    This is the authority on every node, parameter, VEX function and HOM call.
    Read the page before you use an API that you have not confirmed in this
    session: names and enum members change between Houdini releases, and a
    wrong one often fails without a message.

    Do not answer from memory, and do not read sidefx.com yourself.

    The pages come from the Houdini install on this machine, so they match the
    build exactly. The first search on a build indexes it once, which takes a
    few seconds; the index stays on disk. A page read never waits for it.

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

    section: read only the part of a page under one heading, for example
    "Quick renders and flipbooks". A long page lists its headings.

    part: a long page comes in parts of about 20,000 characters. Read the next
    one with part=2, 3 and so on.

    Returns markdown for a page, JSON for a search.
    """
    given = [name for name, value in
             (("query", query), ("page", page), ("node", node)) if value]
    if len(given) != 1:
        return "Give exactly one of query, page or node."

    try:
        docs = reader()
        if query:
            return json.dumps(search(docs, query, limit, category, build), indent=2)
        if node:
            meta = call("docs", {"node": node})
            type_name, node_category = meta.get("type_name", ""), meta.get("category", "")
            path = node_page(type_name, node_category, meta.get("default_help_url"))
            try:
                return excerpt(read(docs, path, build), section, part)
            except ValueError:
                # An asset can carry a help address that has no page, and a
                # version can lack a page of its own. Try the bare type name,
                # never a search: a wrong page is worse than none.
                plain = f"nodes/{node_folder(node_category)}/{type_base_name(type_name)}"
                if plain == path:
                    raise
                return excerpt(read(docs, plain, build), section, part)
        return excerpt(read(docs, page, build), section, part)
    except ImportError:
        return "Error: the documentation engine is not installed. Run: uv pip install houdinimd-docs"
    except (ValueError, RuntimeError) as error:
        return f"Error: {error}"


_reader = None


def reader():
    """The one documentation reader of this process. It scans for installs
    once and keeps the index open, so only the first call pays for either."""
    global _reader
    if _reader is None:
        import houdinimd_docs
        _reader = houdinimd_docs.Docs(data_dir())
    return _reader


def data_dir() -> str:
    """HoudiniMCP's own folder, where the documentation index lives. The index
    fills once per Houdini build, the first time a search needs it."""
    home = os.path.expanduser("~")
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        return os.path.join(base, "HoudiniMCP")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "HoudiniMCP")
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(base, "houdinimcp")


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


def node_folder(category: str) -> str:
    return CATEGORY_TO_DIR.get(category, category.lower())


def node_page(type_name: str, category: str, help_url: str = None) -> str:
    """The page path for a node type.

    The node type's own help URL wins ('operator:Sop/attribwrangle'). Without
    one, the page is built from the type name and category the way the help
    names it: ('labs::edge_damage::2.0', 'Sop') -> 'nodes/sop/labs--edge_damage-2.0'.
    """
    if help_url:
        # 'operator:Sop/edge_damage?namespace=labs&version=2.1'
        match = re.match(r"operator:([^/?]+)/([^?]+)(?:\?(.*))?", help_url)
        if match:
            category, name, query = match.groups()
            fields = dict(parse_qsl(query or ""))
            type_name = "::".join(filter(None, (fields.get("namespace"), name, fields.get("version"))))
        elif "://" in help_url:
            return normalize_page(help_url)
    name, version = re.fullmatch(r"(.*?)(?:::(\d+(?:\.\d+)*))?", type_name).groups()
    page = name.replace("::", "--") + (f"-{version}" if version else "")
    return f"nodes/{node_folder(category)}/{page}"


def heading(line: str):
    """(level, title) when the line is a heading, in markdown ('## Methods')
    or in HTML ('<h3 id="methods">Methods</h3>'), else None."""
    match = re.match(r"(#{2,4}) +(.+)", line)
    if match:
        return len(match.group(1)), match.group(2).strip()
    match = re.match(r"\s*<h([2-4])\b[^>]*>(.*?)</h\1>", line)
    if match:
        return int(match.group(1)), re.sub(r"<[^>]+>", "", match.group(2)).strip()
    return None


def excerpt(text: str, section: str = None, part: int = 1) -> str:
    """One answer's worth of a page: the sections whose heading holds
    `section`, cut into parts of at most LIMIT characters at line ends."""
    lines = text.splitlines(keepends=True)
    marks = [(index, found) for index, found in
             ((index, heading(line)) for index, line in enumerate(lines)) if found]
    headings = [title for _, (_, title) in marks]
    if section:
        found = []
        for number, (start, (level, title)) in enumerate(marks):
            if section.lower() in title.lower():
                # A section runs to the next heading of its own level or above.
                end = next((index for index, (other, _) in marks[number + 1:] if other <= level),
                           len(lines))
                found.append("".join(lines[start:end]))
        if not found:
            return f"Error: no section '{section}'. Sections: {'; '.join(headings)}"
        text = "\n".join(found)

    # ponytail: one line longer than LIMIT stays whole. Cut inside the line if
    # a page ever carries one.
    parts, current = [], ""
    for line in text.splitlines(keepends=True):
        if current and len(current) + len(line) > LIMIT:
            parts.append(current)
            current = ""
        current += line
    parts.append(current)

    if len(parts) == 1:
        return text
    if not 1 <= part <= len(parts):
        return f"Error: part must be 1 to {len(parts)}."
    where = (f"Read the next with part={part + 1}" if part < len(parts) else "This is the last part")
    return (parts[part - 1].rstrip() + f"\n\n---\nPart {part} of {len(parts)}. {where}, "
            f"or one section with section=. Sections: {'; '.join(headings)}.")


if __name__ == "__main__":
    assert node_page("labs::edge_damage::2.0", "Sop") == "nodes/sop/labs--edge_damage-2.0"
    assert node_page("attribwrangle", "Sop") == "nodes/sop/attribwrangle"
    assert node_page("geo", "Object") == "nodes/obj/geo"
    assert node_page("x", "Sop", "operator:Sop/autouv?namespace=labs") == "nodes/sop/labs--autouv"
    assert node_page("x", "Sop", "operator:Sop/edge_damage?namespace=labs&version=2.1") == "nodes/sop/labs--edge_damage-2.1"
    assert node_page("x", "Sop", "operator:Sop/copytopoints?version=2.0") == "nodes/sop/copytopoints-2.0"
    assert node_page("x", "Sop", "https://www.sidefx.com/docs/houdini/nodes/sop/box.html") == "nodes/sop/box"
    assert type_base_name("labs::edge_damage::2.0") == "edge_damage"
    page = "# T\n\nintro\n\n## Alpha\n\n" + "a line\n" * 4000 + "## Beta\n\nb\n"
    assert excerpt("short") == "short"
    first = excerpt(page)
    assert len(first) < LIMIT + 500 and "Part 1 of 2. Read the next with part=2" in first
    assert "This is the last part" in excerpt(page, part=2)
    assert excerpt(page, section="beta") == "## Beta\n\nb\n"
    assert excerpt(page, section="gamma").startswith("Error: no section 'gamma'. Sections: Alpha; Beta")
    assert excerpt(page, part=3) == "Error: part must be 1 to 2."
    # houdinimd.com writes a class page's headings as HTML, and an empty
    # section is two headings in a row.
    html = ('# C\n\n<h2 id="m">Methods</h2>\n\n<h3 id="a">Memories</h3>\n'
            '<h3 id="q">Quick renders and <code>flipbooks</code></h3>\n\nflip\n\n<h3>Window</h3>\nw\n')
    assert excerpt(html, section="quick renders") == '<h3 id="q">Quick renders and <code>flipbooks</code></h3>\n\nflip\n\n'
    assert excerpt(html, section="memories") == '<h3 id="a">Memories</h3>\n'
    assert excerpt(html, section="methods").endswith("w\n")
    assert excerpt(html, section="nope").endswith("Methods; Memories; Quick renders and flipbooks; Window")
    print("ok")
