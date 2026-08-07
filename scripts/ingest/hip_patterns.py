"""
Houdini .hip Pattern Extraction
================================
Extracts searchable patterns (scene graphs, subgraphs, node recipes)
from parsed .hip/.hda data. No external dependencies — stdlib only.

Input:  hip_parsed.json / hda_parsed.json (list of parsed scene dicts)
Output: hip_patterns/ directory with text files, hip_patterns_index.json manifest
"""

import hashlib
import json
import os
from collections import defaultdict


def _hash(*parts):
    """Stable short hash from string parts."""
    blob = "\n".join(str(p) for p in parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


def _format_params(params):
    """Format a parameter dict into a compact string."""
    if not params:
        return ""
    parts = []
    for k, v in sorted(params.items()):
        if isinstance(v, list):
            parts.append(f"{k}: {' '.join(v)}")
        else:
            parts.append(f"{k}: {v}")
    return ", ".join(parts)


def _network_context(path):
    """Return the parent network path for a node path.

    E.g. '/obj/geo1/box1' → '/obj/geo1'
    """
    return path.rsplit("/", 1)[0] or "/"


def _source_label(source):
    """Extract a human-readable label from a file path.

    '/opt/hfs21.0/.../nodes/sop/copy.hip' → 'copy'
    '/opt/hfs21.0/.../AttributePromote.hda' → 'AttributePromote'
    """
    basename = os.path.basename(source)
    name, _ = os.path.splitext(basename)
    return name


def _format_annotations(scene, context=None):
    """Format sticky notes, node comments, and netbox labels as text lines.

    If context is given, only include annotations matching that context.
    Returns a list of text lines (may be empty).
    """
    lines = []

    # Sticky notes
    for sn in scene.get("sticky_notes", []):
        if context and sn["context"] != context:
            continue
        lines.append(f"  [note] {sn['text']}")

    # Network box labels
    for nb in scene.get("netboxes", []):
        if context and nb["context"] != context:
            continue
        lines.append(f"  [section] {nb['label']}")

    # Node comments (only when showing full scene, not context-filtered)
    if not context:
        for node in scene.get("nodes", []):
            comment = node.get("comment", "")
            if comment:
                lines.append(f"  [comment on {node['name']}] {comment}")

    return lines


def _extract_scene_graph(scene):
    """Extract one scene-graph pattern per source file."""
    source = scene["source"]
    nodes = scene["nodes"]
    connections = scene["connections"]

    if not nodes:
        return None

    label = _source_label(source)
    lines = [
        f"Pattern: Scene Graph",
        f"Source: {source}",
        f"Name: {label}",
        f"Category: SCENE",
    ]

    # Annotations (sticky notes, comments, netbox labels)
    annotations = _format_annotations(scene)
    if annotations:
        lines.append("")
        lines.append("Notes:")
        lines.extend(annotations)

    lines.append("")
    lines.append("Nodes:")
    for node in nodes:
        param_str = _format_params(node.get("parameters", {}))
        comment = node.get("comment", "")
        suffix = f" — {param_str}" if param_str else ""
        if comment:
            suffix += f" // {comment}"
        lines.append(f"  {node['name']} ({node['category']}) [{node['type']}]{suffix}")

    if connections:
        lines.append("")
        lines.append("Connections:")
        path_to_name = {n["path"]: n["name"] for n in nodes}
        for conn in connections:
            src = path_to_name.get(conn["src_path"], conn["src_path"])
            dst = path_to_name.get(conn["dst_path"], conn["dst_path"])
            lines.append(f"  {src} → {dst} (input {conn['dst_input']})")

    text = "\n".join(lines)
    pattern_id = f"scene_{_hash(source)}"

    return {
        "id": pattern_id,
        "type": "scene",
        "source": [source],
        "context": "/",
        "node_count": len(nodes),
        "text": text,
    }


def _extract_subgraphs(scene):
    """Extract connected-component subgraphs within each network context."""
    nodes = scene["nodes"]
    connections = scene["connections"]
    source = scene["source"]

    if not nodes:
        return []

    # Group nodes by their parent network
    context_nodes = defaultdict(list)
    for node in nodes:
        ctx = _network_context(node["path"])
        context_nodes[ctx].append(node)

    # Group connections by context (derived from dst_path)
    context_conns = defaultdict(list)
    for conn in connections:
        ctx = _network_context(conn["dst_path"])
        context_conns[ctx].append(conn)

    patterns = []

    for ctx, ctx_node_list in context_nodes.items():
        conns = context_conns.get(ctx, [])
        if len(ctx_node_list) < 2:
            continue

        # Build adjacency (undirected) for connected components
        path_set = {n["path"] for n in ctx_node_list}
        adj = defaultdict(set)
        for conn in conns:
            if conn["src_path"] in path_set and conn["dst_path"] in path_set:
                adj[conn["src_path"]].add(conn["dst_path"])
                adj[conn["dst_path"]].add(conn["src_path"])

        # Find connected components via BFS
        visited = set()
        components = []
        for node in ctx_node_list:
            p = node["path"]
            if p in visited:
                continue
            # BFS from this node
            queue = [p]
            component = set()
            while queue:
                cur = queue.pop(0)
                if cur in visited:
                    continue
                visited.add(cur)
                component.add(cur)
                for neighbor in adj.get(cur, []):
                    if neighbor not in visited:
                        queue.append(neighbor)
            if len(component) >= 2:
                components.append(component)

        # Build a pattern per connected component
        node_by_path = {n["path"]: n for n in ctx_node_list}
        for comp_paths in components:
            comp_nodes = [node_by_path[p] for p in sorted(comp_paths)]
            comp_conns = [
                c for c in conns
                if c["src_path"] in comp_paths and c["dst_path"] in comp_paths
            ]

            # Dedup key: sorted types + sorted connection tuples (by type, not name)
            path_to_type = {n["path"]: n["type"] for n in comp_nodes}
            types_key = tuple(sorted(n["type"] for n in comp_nodes))
            conns_key = tuple(sorted(
                (path_to_type.get(c["src_path"], "?"),
                 path_to_type.get(c["dst_path"], "?"),
                 c["src_output"], c["dst_input"])
                for c in comp_conns
            ))
            dedup_key = (types_key, conns_key)

            # Determine category from first node
            category = comp_nodes[0]["category"] if comp_nodes else "UNKNOWN"

            label = _source_label(source)
            lines = [
                f"Pattern: {category} Chain",
                f"Source: {source}",
                f"Name: {label}",
                f"Context: {ctx}",
                f"Category: {category}",
            ]

            # Context-scoped annotations
            annotations = _format_annotations(scene, context=ctx)
            if annotations:
                lines.append("")
                lines.append("Notes:")
                lines.extend(annotations)

            lines.append("")
            lines.append("Nodes:")
            for node in comp_nodes:
                param_str = _format_params(node.get("parameters", {}))
                comment = node.get("comment", "")
                suffix = f" — {param_str}" if param_str else ""
                if comment:
                    suffix += f" // {comment}"
                lines.append(f"  {node['name']} ({node['category']}) [{node['type']}]{suffix}")

            if comp_conns:
                lines.append("")
                lines.append("Connections:")
                for conn in comp_conns:
                    src = conn["src_path"].rsplit("/", 1)[-1]
                    dst = conn["dst_path"].rsplit("/", 1)[-1]
                    lines.append(f"  {src} → {dst} (input {conn['dst_input']})")

            text = "\n".join(lines)
            pattern_id = f"subgraph_{_hash(str(dedup_key))}"

            patterns.append({
                "id": pattern_id,
                "type": "subgraph",
                "source": [source],
                "context": ctx,
                "node_count": len(comp_nodes),
                "text": text,
                "dedup_key": dedup_key,
            })

    return patterns


def _extract_recipes(scene):
    """Extract unique (type, non-default params) node recipes."""
    recipes = []
    source = scene["source"]

    for node in scene["nodes"]:
        params = node.get("parameters", {})
        if not params:
            continue

        # Dedup key: (type, sorted param items)
        params_key = tuple(sorted(
            (k, tuple(v) if isinstance(v, list) else v)
            for k, v in params.items()
        ))
        dedup_key = (node["type"], params_key)

        category = node["category"]
        param_str = _format_params(params)
        comment = node.get("comment", "")
        label = _source_label(source)

        lines = [
            f"Pattern: {node['type']} Recipe",
            f"Source: {source}",
            f"Name: {label}",
            f"Context: {_network_context(node['path'])}",
            f"Category: {category}",
            "",
            "Nodes:",
            f"  {node['name']} ({category}) [{node['type']}] — {param_str}",
        ]
        if comment:
            lines.append(f"  // {comment}")
        text = "\n".join(lines)
        pattern_id = f"recipe_{_hash(str(dedup_key))}"

        recipes.append({
            "id": pattern_id,
            "type": "recipe",
            "source": [source],
            "context": _network_context(node["path"]),
            "node_count": 1,
            "text": text,
            "dedup_key": dedup_key,
        })

    return recipes


def extract_patterns(parsed_scenes):
    """Extract all pattern types from a list of parsed scene dicts.

    Returns a list of pattern dicts with keys:
        id, type, source, context, node_count, text
    Subgraphs and recipes are deduplicated across scenes.
    """
    all_patterns = []

    # Scene graphs — one per file, no dedup needed
    for scene in parsed_scenes:
        sg = _extract_scene_graph(scene)
        if sg:
            all_patterns.append(sg)

    # Subgraphs — collect, then dedup by topology
    raw_subgraphs = []
    for scene in parsed_scenes:
        raw_subgraphs.extend(_extract_subgraphs(scene))

    deduped_subgraphs = {}
    for sg in raw_subgraphs:
        key = sg["dedup_key"]
        if key in deduped_subgraphs:
            # Merge sources
            existing = deduped_subgraphs[key]
            for src in sg["source"]:
                if src not in existing["source"]:
                    existing["source"].append(src)
        else:
            deduped_subgraphs[key] = sg

    for sg in deduped_subgraphs.values():
        del sg["dedup_key"]
        all_patterns.append(sg)

    # Recipes — collect, then dedup
    raw_recipes = []
    for scene in parsed_scenes:
        raw_recipes.extend(_extract_recipes(scene))

    deduped_recipes = {}
    for r in raw_recipes:
        key = r["dedup_key"]
        if key in deduped_recipes:
            existing = deduped_recipes[key]
            for src in r["source"]:
                if src not in existing["source"]:
                    existing["source"].append(src)
        else:
            deduped_recipes[key] = r

    for r in deduped_recipes.values():
        del r["dedup_key"]
        all_patterns.append(r)

    return all_patterns


def write_patterns(patterns, output_dir):
    """Write each pattern as a text file to output_dir.

    Returns the number of files written.
    """
    os.makedirs(output_dir, exist_ok=True)
    for pattern in patterns:
        filepath = os.path.join(output_dir, f"{pattern['id']}.txt")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(pattern["text"])
    return len(patterns)


def build_patterns_index(patterns, output_path):
    """Write a lightweight manifest JSON for the patterns.

    Each entry: {id, type, source, context, node_count}
    """
    entries = []
    for p in patterns:
        entries.append({
            "id": p["id"],
            "type": p["type"],
            "source": p["source"],
            "context": p.get("context", "/"),
            "node_count": p["node_count"],
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)

    return entries
