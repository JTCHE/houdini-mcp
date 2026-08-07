"""Houdini documentation, read live from HoudiniMD (https://houdinimd.com).

There is no local corpus. Search is the site's BM25 endpoint, a page is raw
markdown at /docs/<page>.md, and /api/resolve turns a loose name into a page.
Set HOUDINIMD_BASE to point at another origin.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("HOUDINIMD_BASE", "https://houdinimd.com").rstrip("/")

_TIMEOUT = 20
_HEADERS = {"User-Agent": "HoudiniMCP", "Accept": "text/markdown, application/json"}

# hou node category name -> documentation subdirectory, where the two differ.
_CATEGORY_TO_DIR = {
    "Object": "obj",
    "Driver": "out",
    "Manager": "mgr",
    "CopNet": "cop2",
    "VopNet": "vop",
    "Shop": "shop",
}


def _fetch(url: str, timeout: int = _TIMEOUT) -> str:
    request = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def page_url(page: str) -> str:
    return f"{BASE}/docs/{urllib.parse.quote(page)}.md"


def normalize_page(reference: str) -> str:
    """Turn any reference to a documentation page into a HoudiniMD page path.

    Accepts a page path, a HoudiniMD or SideFX URL, and a trailing .md or .html.
    Every HoudiniMD page lives under `houdini/`, so a bare path gets the prefix.
    """
    page = re.sub(r"^https?://[^/]+/", "", reference.strip())
    page = re.sub(r"^(docs|api/raw)/", "", page.strip("/"))
    page = re.sub(r"\.(md|html)$", "", page).strip("/")
    if not page.startswith("houdini/"):
        page = f"houdini/{page}"
    return page


def search(query: str, limit: int = 5, category: str = None) -> list | dict:
    """Rank documentation pages for a query with the site's BM25 search.

    Returns a list of {path, title, summary, category, version, score} or
    {"error": ...}.
    """
    params = {"q": query, "limit": limit}
    if category:
        params["category"] = category
    url = f"{BASE}/api/search?{urllib.parse.urlencode(params)}"
    try:
        body = json.loads(_fetch(url))
    except Exception as error:
        return {"error": f"{error} ({url})"}
    return [
        {key: hit[key] for key in ("path", "title", "summary", "category", "version", "score") if key in hit}
        for hit in body.get("results", [])
    ]


def resolve(name: str) -> str | None:
    """Ask the site which page a loose name means, e.g. 'pyro solver'."""
    url = f"{BASE}/api/resolve?{urllib.parse.urlencode({'name': name})}"
    try:
        return json.loads(_fetch(url)).get("slug")
    except Exception:
        return None


def get_page(reference: str) -> dict:
    """Fetch the markdown of a documentation page.

    Returns {page, url, content}, or {error, page}. A reference with no path in
    it is a name, so it goes through /api/resolve. A path that does not exist
    reports the site's own suggestions — resolving it by name matches loosely
    enough to answer a wrong path with an unrelated page.
    """
    page = normalize_page(reference)
    is_name = "/" not in reference.strip("/")
    try:
        return {"page": page, "url": page_url(page), "content": _fetch(page_url(page))}
    except urllib.error.HTTPError as error:
        if error.code != 404:
            return {"error": f"HTTP {error.code}", "page": page}
        suggestions = error.read().decode("utf-8", errors="replace")
    except Exception as error:
        return {"error": str(error), "page": page}

    slug = resolve(reference) if is_name else None
    if not slug or slug == page:
        return {"error": suggestions.replace("\n", " ").strip(), "page": page}
    try:
        return {"page": slug, "url": page_url(slug), "content": _fetch(page_url(slug))}
    except Exception as error:
        return {"error": str(error), "page": slug}


def type_base_name(type_name: str) -> str:
    """Strip the namespace and version: 'labs::attribwrangle::2.0' -> 'attribwrangle'."""
    return re.sub(r"::\d+(\.\d+)*$", "", type_name).split("::")[-1].strip("_")


def node_page(type_name: str, category: str, help_url: str = None) -> str:
    """Build the documentation page path for a node type.

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
    subdirectory = _CATEGORY_TO_DIR.get(category, category.lower())
    return f"houdini/nodes/{subdirectory}/{type_base_name(type_name)}"
