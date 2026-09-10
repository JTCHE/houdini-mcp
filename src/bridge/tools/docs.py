"""docs — the official Houdini documentation."""
import json
import re

from ..connection import call

# Characters in one answer. A client drops a tool result much longer than this,
# and hou.Geometry alone is 140,000.
LIMIT = 20_000


def tool(query: str = None, page: str = None, node: str = None,
         category: str = None, limit: int = 5, section: str = None,
         part: int = 1) -> str:
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

    section: read only the part of a page under one heading, for example
    "Quick renders and flipbooks". A long page lists its headings.

    part: a long page comes in parts of about 20,000 characters. Read the next
    one with part=2, 3 and so on.

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
            return excerpt(result["content"], section, part)
        return f"Error: {result['error']} ({page})"

    result = houdini_docs.get_page(page)
    if "error" in result:
        return f"Error: {result['error']} ({result['page']})"
    return excerpt(result["content"], section, part)


def excerpt(text: str, section: str = None, part: int = 1) -> str:
    """One answer's worth of a page: the sections whose heading holds
    `section`, cut into parts of at most LIMIT characters at line ends."""
    headings = [line[3:].strip() for line in text.splitlines() if line.startswith("## ")]
    if section:
        chunks = re.split(r"(?m)^(?=## )", text)
        found = [chunk for chunk in chunks if chunk.startswith("## ")
                 and section.lower() in chunk.splitlines()[0].lower()]
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
    page = "# T\n\nintro\n\n## Alpha\n\n" + "a line\n" * 4000 + "## Beta\n\nb\n"
    assert excerpt("short") == "short"
    first = excerpt(page)
    assert len(first) < LIMIT + 500 and "Part 1 of 2. Read the next with part=2" in first
    assert "This is the last part" in excerpt(page, part=2)
    assert excerpt(page, section="beta") == "## Beta\n\nb\n"
    assert excerpt(page, section="gamma").startswith("Error: no section 'gamma'. Sections: Alpha; Beta")
    assert excerpt(page, part=3) == "Error: part must be 1 to 2."
    print("ok")
