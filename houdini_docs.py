"""
On-demand proxy for Houdini documentation via houdinimd.jchd.me.

No bundled corpus — fetches markdown on request, caches sitemap locally.
Override base URL with HOUDINIMCP_DOCS_BASE env var.
"""
import json
import os
import re
import time
import urllib.request
import urllib.error
from pathlib import Path

DOCS_BASE = os.environ.get(
    "HOUDINIMCP_DOCS_BASE",
    "https://houdinimd.jchd.me/docs/houdini",
).rstrip("/")

_SITEMAP_URL = "https://houdinimd.jchd.me/sitemap.xml"
_CACHE_DIR = Path.home() / ".cache" / "houdinimcp"
_SITEMAP_CACHE = _CACHE_DIR / "sitemap.json"
_SITEMAP_TTL = 7 * 24 * 3600  # 1 week

_CATEGORY_TO_DIR = {
    "Sop": "sop",
    "Object": "obj",
    "Dop": "dop",
    "Cop2": "cop",
    "CopNet": "cop",
    "Driver": "out",
    "Lop": "lop",
    "Vop": "vop",
    "VopNet": "vop",
    "Chop": "chop",
    "Top": "top",
    "Shop": "shop",
    "Manager": "mgr",
}

# In-process sitemap cache — populated on first search call
_sitemap: list | None = None


def _fetch_url(url: str, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "HoudiniMCP/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _load_sitemap() -> list:
    """Return list of URL path strings from cache, refreshing from remote if stale."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if _SITEMAP_CACHE.exists():
        age = time.time() - _SITEMAP_CACHE.stat().st_mtime
        if age < _SITEMAP_TTL:
            with open(_SITEMAP_CACHE, encoding="utf-8") as f:
                return json.load(f)

    try:
        xml = _fetch_url(_SITEMAP_URL, timeout=15)
        base = "https://houdinimd.jchd.me/"
        paths = [
            m.group(1).strip()[len(base):]
            for m in re.finditer(r"<loc>([^<]+)</loc>", xml)
            if m.group(1).strip().startswith(base)
        ]
        with open(_SITEMAP_CACHE, "w", encoding="utf-8") as f:
            json.dump(paths, f)
        return paths
    except Exception:
        # Return stale cache if remote fetch fails
        if _SITEMAP_CACHE.exists():
            with open(_SITEMAP_CACHE, encoding="utf-8") as f:
                return json.load(f)
        return []


def _get_sitemap() -> list:
    global _sitemap
    if _sitemap is None:
        _sitemap = _load_sitemap()
    return _sitemap


def get_doc_content(path: str, timeout: int = 10) -> dict:
    """Fetch markdown for a doc path, e.g. 'nodes/sop/attribwrangle'.

    Accepts full sitemap paths (docs/houdini/...) or bare paths (nodes/sop/...).
    Returns {path, url, content} on success or {error, path} on failure.
    """
    path = path.strip("/").removesuffix(".md")
    # Accept raw sitemap paths like docs/houdini/nodes/sop/attribwrangle
    _PREFIX = "docs/houdini/"
    if path.startswith(_PREFIX):
        path = path[len(_PREFIX):]
    url = f"{DOCS_BASE}/{path}.md"
    try:
        content = _fetch_url(url, timeout=timeout)
        return {"path": path, "url": url, "content": content}
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "path": path}
    except Exception as e:
        return {"error": str(e), "path": path}


def search_docs(query: str, top_k: int = 5) -> list | dict:
    """Search doc paths by token overlap against the sitemap slugs.

    Returns a list of {path, title, url, score} or {error} if sitemap unavailable.
    """
    paths = _get_sitemap()
    if not paths:
        return {"error": "Could not load sitemap from houdinimd.jchd.me"}

    q_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    if not q_tokens:
        return []

    _PREFIX = "docs/houdini/"
    scored = []
    for raw_path in paths:
        slug_tokens = set(re.findall(r"[a-z0-9]+", raw_path.lower()))
        overlap = len(q_tokens & slug_tokens)
        if overlap == 0:
            continue
        # Bonus for exact substring match
        score = overlap + (2 if query.lower() in raw_path.lower() else 0)
        # Normalize: strip docs/houdini/ prefix for consistency with resolve_node_doc
        norm = raw_path[len(_PREFIX):] if raw_path.startswith(_PREFIX) else raw_path
        title = norm.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ")
        scored.append({
            "path": norm,
            "title": title,
            "url": f"https://houdinimd.jchd.me/{raw_path}",
            "score": score,
        })

    scored.sort(key=lambda x: -x["score"])
    return scored[:top_k]


def resolve_node_doc(type_name: str, category: str) -> str:
    """Build a doc path from a node type name and category.

    e.g. resolve_node_doc('attribwrangle', 'Sop') → 'nodes/sop/attribwrangle'
    Strips namespaces (labs::name::2.0 → name).
    """
    # Strip namespace and version (e.g. "labs::attribwrangle::2.0" → "attribwrangle")
    name = type_name.split("::")[-1] if "::" in type_name else type_name
    name = re.sub(r"\d+\.\d+$", "", name).strip("_")
    subdir = _CATEGORY_TO_DIR.get(category, category.lower())
    return f"nodes/{subdir}/{name}"


def parse_help_url(default_help_url: str) -> str | None:
    """Convert a Houdini defaultHelpUrl to a doc path.

    e.g. 'operator:Sop/attribwrangle' → 'nodes/sop/attribwrangle'
    """
    if not default_help_url:
        return None
    # Format: operator:Category/typename or operator:Category/typename::version
    m = re.match(r"operator:([^/]+)/(.+)", default_help_url)
    if not m:
        return None
    category, name = m.group(1), m.group(2)
    name = re.sub(r"::\d+\.\d+$", "", name)
    subdir = _CATEGORY_TO_DIR.get(category, category.lower())
    return f"nodes/{subdir}/{name}"


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        q = " ".join(sys.argv[2:])
        results = search_docs(q)
        if isinstance(results, dict):
            print(results.get("error"))
        else:
            for r in results:
                print(f"[{r['score']}] {r['title']}  {r['path']}")
    elif len(sys.argv) > 1 and sys.argv[1] == "get":
        r = get_doc_content(sys.argv[2])
        if "error" in r:
            print(r["error"])
        else:
            print(r["content"][:2000])
    else:
        print("Usage: python houdini_docs.py search <query>")
        print("       python houdini_docs.py get <path>")
