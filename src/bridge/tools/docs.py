"""docs — the official Houdini documentation."""
import difflib
import json
import os
import re
import sys
from urllib.parse import parse_qsl

from houdinimcp import protocol

from ..connection import call, last_version

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
                "/obj/geo1/attribwrangle1", or a node type name, for example
                "mountain". Returns the page of that node type. A path is the
                only input that needs Houdini. With a type name, `category`
                picks the context: "sop", "lop", "obj" and so on.

    category: keep the search inside one folder of pages, for example
    "nodes/sop", "vex/functions" or "hom/hou".

    build: read a specific Houdini build, for example "21.0.829". Default: the
    build of the Houdini this bridge talks to, so the page matches the session
    you work in. Without a session, the Houdini in $HFS, then the newest build
    on this machine.

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

    build = build or last_version()
    try:
        docs = reader()
        if query:
            return json.dumps(search(docs, query, limit, category, build), separators=(",", ":"))
        if node and "/" not in node:
            folder = (category or "").strip("/").removeprefix("nodes/")
            return excerpt(read(docs, node, build, folder), section, part, always="Inputs")
        if node:
            meta = call("docs", {"node": node})
            type_name, node_category = meta.get("type_name", ""), meta.get("category", "")
            path = node_page(type_name, node_category, meta.get("default_help_url"))
            try:
                return excerpt(read(docs, path, build), section, part, always="Inputs")
            except ValueError:
                # An asset can carry a help address that has no page, and a
                # version can lack a page of its own. Try the bare type name,
                # never a search: a wrong page is worse than none.
                plain = f"nodes/{node_folder(node_category)}/{type_base_name(type_name)}"
                if plain == path:
                    raise
                return excerpt(read(docs, plain, build), section, part, always="Inputs")
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
        # The same folder that holds the session files. One definition, in
        # protocol, so the two never drift apart.
        _reader = houdinimd_docs.Docs(protocol.data_dir())
    return _reader


# Words that carry no meaning in a search and that every page holds anyway.
COMMON = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
          "how", "do", "does", "i", "my", "is", "it", "that", "this", "can",
          "what", "when", "use", "using", "houdini", "node", "nodes"}


def search(engine, query, limit, category, build):
    # ponytail: the category is a filter after the ranking, so a narrow folder
    # needs the wide fetch. Push it into the SQL if a filter comes back short.
    wanted = max(limit * 40, 200) if category else limit
    hits = json.loads(engine.search(query, wanted, build))
    searched = query
    if not hits:
        # Every word must match, so a question written as a sentence matches
        # nothing at all. Ask for the words one at a time instead and keep the
        # best score of each page: one word that matches nothing then costs
        # nothing, where in one OR query it loses every other word with it.
        words = [word for word in re.findall(r"[\w:.]+", query.lower())
                 if word not in COMMON and len(word) > 2][:6]
        if words:
            searched = ", ".join(words)
            hits = _best_of(engine, words, wanted, build)
    if category:
        prefix = category.strip("/") + "/"
        hits = [hit for hit in hits if hit["path"].startswith(prefix)]
    hits = hits[:limit]
    if not hits:
        return {"query": query, "searched": searched, "hits": [],
                "note": ("Nothing in the documentation matched. Try fewer words, "
                         "or the name of the node or the function itself."
                         if not category else
                         f"Nothing under '{category}' matched. Search without a "
                         f"category, or use another folder.")}
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


def _best_of(engine, words, wanted, build):
    """One search for each word, merged: a page keeps its best score, and a
    page that answers to more than one word comes first."""
    found = {}
    for word in words:
        try:
            for hit in json.loads(engine.search(word, wanted, build)):
                seen = found.get(hit["path"])
                if seen is None:
                    hit["words"] = 1
                    found[hit["path"]] = hit
                else:
                    seen["words"] += 1
                    seen["score"] = max(seen["score"], hit["score"])
        except ValueError:
            continue
    return sorted(found.values(), key=lambda hit: (hit["words"], hit["score"]), reverse=True)


# The node contexts in the order a bare name most likely means.
NODE_FOLDERS = ("sop", "obj", "lop", "dop", "cop", "top", "chop", "vop", "out", "cop2")


def read(engine, reference, build, folder=None):
    """The page as markdown. A reference with no path in it is a name: the node
    page of that name comes first, in `folder` when one is given, then the best
    search hit. "mountain" is the node, not the shelf tool of that name."""
    path = normalize_page(reference)
    try:
        view = json.loads(engine.page(path, build))
    except ValueError:
        if "/" in path:
            raise
        view = json.loads(_page_of_name(engine, path, build, folder))
    head = [f"# {view['name']}"]
    if view.get("nodeType"):
        head.append(f"*{view['nodeType']}*")
    if view.get("summary"):
        head.append(view["summary"])
    head.append(f"Page `{view['path']}`, Houdini {view['version']}.")
    return "\n\n".join(head) + "\n\n" + view["markdown"]


def _page_of_name(engine, name, build, folder=None):
    """The page JSON for a bare name."""
    if name.startswith("hou."):
        return engine.page(f"hom/hou/{name[4:]}", build)
    for candidate in ((folder,) if folder else NODE_FOLDERS):
        try:
            return engine.page(f"nodes/{candidate}/{name}", build)
        except ValueError:
            continue
    hits = json.loads(engine.search(name, 20, build))
    if folder:
        hits = [hit for hit in hits if hit["path"].startswith(f"nodes/{folder}/")]
    if not hits:
        raise ValueError(f"No page for '{name}'. Search for it with query.")
    named = [hit for hit in hits if hit["path"].rsplit("/", 1)[-1] == name]
    nodes = [hit for hit in named if hit["path"].startswith("nodes/")]
    if folder and not named:
        raise ValueError(f"No page 'nodes/{folder}/{name}'. Close pages: "
                         f"{', '.join(hit['path'] for hit in hits[:5])}")
    return engine.page((nodes or named or hits)[0]["path"], build)


def normalize_page(reference: str) -> str:
    """Turn any reference to a documentation page into a page path.

    Accepts a page path, a NodebookMD, HoudiniMD or SideFX address, and a trailing .md or
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


# The label of a parameter folder is not always the heading of the section that
# documents it. These are the ones that differ on most node pages.
FOLDER_HEADINGS = {
    "geometry": "Parameters",
    "attributes": "Attributes",
    "bindings": "Bindings",
    "code": "Code",
    "output": "Output",
    "inputs": "Inputs",
    "advanced": "Advanced",
}


def _contents(lines, marks):
    """A map of a page: each heading with the size of its section.

    A page of 80,000 characters comes in parts, and a reader that must guess
    which part holds one method reads them all. The size says which section is
    worth a call.
    """
    if not marks:
        return "The page has no headings."
    rows = []
    for number, (start, (level, title)) in enumerate(marks):
        size = len(_cut(lines, marks, number, start, level))
        rows.append(f"{'  ' * (level - 2)}{title} ({size} characters)")
    return "Sections, with the size of each:\n" + "\n".join(rows)


def _cut(lines, marks, number, start, level):
    """The lines of one section: down to the next heading of its level or above."""
    end = next((index for index, (other, _) in marks[number + 1:] if other <= level),
               len(lines))
    return "".join(lines[start:end])


def _sections(lines, marks, wanted):
    """Every section whose heading matches, with the nearest name when none does.

    A heading is rarely spelled the way a caller asks for it, and an answer of
    "no such section" for a page that holds the answer is the costly failure.
    """
    wanted = FOLDER_HEADINGS.get(wanted.strip().lower(), wanted).strip().lower()
    found = [_cut(lines, marks, number, start, level)
             for number, (start, (level, title)) in enumerate(marks)
             if wanted in title.lower()]
    if found:
        return found, None
    titles = [title for _, (_, title) in marks]
    near = difflib.get_close_matches(wanted, [title.lower() for title in titles], 1, 0.5)
    if not near:
        return [], None
    return ([_cut(lines, marks, number, start, level)
             for number, (start, (level, title)) in enumerate(marks)
             if title.lower() == near[0]],
            f"No section matched exactly; this is '{near[0]}'.")


def excerpt(text: str, section: str = None, part: int = 1, always: str = None) -> str:
    """One answer's worth of a page: the sections whose heading holds
    `section`, cut into parts of at most LIMIT characters at line ends.

    `always` names a section to add whatever else was asked for. A node page
    answers half a question without its Inputs: what the node takes decides how
    to wire it.
    """
    lines = text.splitlines(keepends=True)
    marks = [(index, found) for index, found in
             ((index, heading(line)) for index, line in enumerate(lines)) if found]
    headings = [title for _, (_, title) in marks]
    near_note = None
    if section:
        found, near_note = _sections(lines, marks, section)
        if not found:
            return f"Error: no section '{section}'. Sections: {'; '.join(headings)}"
        if always:
            extra, _ = _sections(lines, marks, always)
            found += [part for part in extra if part not in found]
        text = "\n".join(found)
        if near_note:
            text = near_note + "\n\n" + text

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
    answer = (parts[part - 1].rstrip() + f"\n\n---\nPart {part} of {len(parts)}. {where}, "
              f"or one section with section=.\n\n" + _contents(lines, marks))
    if always and not section:
        # The page is long enough to be cut, so the section that says what the
        # node takes would otherwise be in a part nobody reads.
        extra, _ = _sections(lines, marks, always)
        if extra and extra[0] not in answer:
            answer += f"\n\n---\n{always}, from further down the page:\n\n" + extra[0]
    return answer


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
    # A class page can write its headings as HTML, and an empty
    # section is two headings in a row.
    html = ('# C\n\n<h2 id="m">Methods</h2>\n\n<h3 id="a">Memories</h3>\n'
            '<h3 id="q">Quick renders and <code>flipbooks</code></h3>\n\nflip\n\n<h3>Window</h3>\nw\n')
    assert excerpt(html, section="quick renders") == '<h3 id="q">Quick renders and <code>flipbooks</code></h3>\n\nflip\n\n'
    assert excerpt(html, section="memories") == '<h3 id="a">Memories</h3>\n'
    assert excerpt(html, section="methods").endswith("w\n")
    assert excerpt(html, section="nope").endswith("Methods; Memories; Quick renders and flipbooks; Window")
    print("ok")
