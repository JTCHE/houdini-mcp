"""
Houdini .hip File Parser
========================
Parses .hip files (cpio archives) into structured node/connection data.
No external dependencies — uses only Python standard library.

See docs/hip_format.md for format reference.
"""

import re

# Cpio header: 6-byte magic + 6×7 octal fields + 11-byte mtime + 6-byte namesize + 11-byte filesize = 76 bytes
_HEADER_LEN = 76
_MAGIC = b"070707"

# Context → node category mapping
_CONTEXT_CATEGORIES = {
    "obj": "OBJ",
    "out": "ROP",
    "ch": "CHOP",
    "shop": "SHOP",
    "img": "COP",
    "vex": "VEX",
    "mat": "MAT",
    "stage": "LOP",
    "part": "POP",
}


def _read_sections(data):
    """Parse cpio archive bytes into a dict of {name: body_bytes}."""
    sections = {}
    pos = 0
    length = len(data)

    while pos + _HEADER_LEN <= length:
        # Find next header magic
        if data[pos:pos + 6] != _MAGIC:
            pos += 1
            continue

        header = data[pos:pos + _HEADER_LEN]
        namesize = int(header[59:65], 8)
        filesize = int(header[65:76], 8)

        name_start = pos + _HEADER_LEN
        name_end = name_start + namesize
        if name_end > length:
            break

        name = data[name_start:name_end].rstrip(b"\x00").decode("ascii", errors="replace")

        body_start = name_end
        body_end = body_start + filesize
        if body_end > length:
            break

        body = data[body_start:body_end]
        sections[name] = body
        pos = body_end

    return sections


def _decode_body(body):
    """Decode section body bytes to text, stripping leading nulls."""
    return body.lstrip(b"\x00").decode("ascii", errors="replace")


def _parse_init(body):
    """Parse a .init section → node type string."""
    text = _decode_body(body)
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("type = "):
            return line[7:].strip()
    return None


def _parse_inputs(body):
    """Parse a .def section → list of connection dicts from the inputs block."""
    text = _decode_body(body)
    connections = []
    in_inputs = False
    brace_depth = 0

    for line in text.splitlines():
        stripped = line.strip()

        if stripped == "inputs":
            in_inputs = True
            continue
        if in_inputs and stripped == "{":
            brace_depth += 1
            continue
        if in_inputs and stripped == "}":
            brace_depth -= 1
            if brace_depth <= 0:
                break
            continue

        if in_inputs and brace_depth > 0:
            # Format: <input_idx> \t <source_node> <source_output> <flag>
            parts = stripped.split()
            if len(parts) >= 3:
                src_name = parts[1].strip('"')
                if not src_name:
                    continue
                connections.append({
                    "dst_input": int(parts[0]),
                    "src_name": src_name,
                    "src_output": int(parts[2]),
                })

    return connections


def _parse_comment(body):
    """Parse a .def section → comment string (empty string if none)."""
    text = _decode_body(body)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("comment "):
            # Format: comment "text here"
            val = stripped[8:].strip().strip('"')
            return val
    return ""


def _parse_postit_text(body):
    """Parse a .postitdef section → sticky note text."""
    text = _decode_body(body)
    for line in text.splitlines():
        if line.startswith("text "):
            # Format: text "content" or text content (unquoted single word)
            val = line[5:].strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            return val
    return ""


def _parse_netbox_comment(body):
    """Parse a .netboxinit section → network box label."""
    text = _decode_body(body)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("comment :="):
            # Format: comment := "label text";
            val = stripped[10:].strip().rstrip(";").strip().strip('"')
            return val
    return ""


def _parse_parms(body):
    """Parse a .parm section → dict of {name: value}.

    Skips 'version' line. Returns non-default parameter values.
    """
    text = _decode_body(body)
    params = {}
    in_braces = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "{":
            in_braces = True
            continue
        if stripped == "}":
            break
        if not in_braces:
            continue
        if stripped.startswith("version "):
            continue

        # Format: name [flags] ( value1 value2 ... )
        match = re.match(r"(\S+)\s+(?:\[.*?\]\s+)?\(\s*(.*?)\s*\)", stripped)
        if match:
            name = match.group(1)
            raw_val = match.group(2)
            # Parse values: split on tabs, strip quotes
            values = []
            for v in re.split(r"\t+", raw_val):
                v = v.strip().strip('"')
                if v:
                    values.append(v)
            if len(values) == 1:
                params[name] = values[0]
            elif values:
                params[name] = values

    return params


def _node_category(path):
    """Derive the node category from its path."""
    parts = path.split("/")
    context = parts[0]
    # Nodes nested 2+ levels deep inside obj are SOPs by convention
    if context == "obj" and len(parts) >= 3:
        return "SOP"
    return _CONTEXT_CATEGORIES.get(context, context.upper())


def _build_result(sections, source):
    """Build structured result from parsed cpio sections."""
    # Collect all node paths from .init sections (skip postit nodes)
    node_info = {}  # path → {"type": str}
    for name, body in sections.items():
        if name.endswith(".init") and not name.endswith(".postitinit"):
            node_path = name[:-5]  # strip .init
            node_type = _parse_init(body)
            if node_type:
                node_info[node_path] = {"type": node_type}

    # Build flat node list with parameters and comments
    nodes_by_path = {}
    for path, info in node_info.items():
        name = path.rsplit("/", 1)[-1]
        houdini_path = "/" + path

        params = {}
        parm_key = path + ".parm"
        if parm_key in sections:
            params = _parse_parms(sections[parm_key])

        comment = ""
        def_key = path + ".def"
        if def_key in sections:
            comment = _parse_comment(sections[def_key])

        node = {
            "type": info["type"],
            "path": houdini_path,
            "name": name,
            "category": _node_category(path),
            "parameters": params,
            "children": [],
        }
        if comment:
            node["comment"] = comment

        nodes_by_path[path] = node

    # Build parent-child relationships
    for path in list(nodes_by_path):
        if "/" in path:
            parent_path = path.rsplit("/", 1)[0]
            if parent_path in nodes_by_path:
                nodes_by_path[parent_path]["children"].append(
                    nodes_by_path[path]["path"]
                )

    # Extract connections
    connections = []
    for path in node_info:
        def_key = path + ".def"
        if def_key not in sections:
            continue
        raw_conns = _parse_inputs(sections[def_key])
        for conn in raw_conns:
            # src_name is a sibling name — resolve to full path
            parent = path.rsplit("/", 1)[0] if "/" in path else ""
            src_path = (parent + "/" + conn["src_name"]) if parent else conn["src_name"]
            connections.append({
                "src_path": "/" + src_path,
                "src_output": conn["src_output"],
                "dst_path": "/" + path,
                "dst_input": conn["dst_input"],
            })

    # Extract sticky notes (.postitdef sections)
    sticky_notes = []
    for name, body in sections.items():
        if name.endswith(".postitdef"):
            note_text = _parse_postit_text(body)
            if note_text:
                # Derive context from path: stage/__stickynote1.postitdef → /stage
                postit_path = name[:-10]  # strip .postitdef
                context = "/" + (postit_path.rsplit("/", 1)[0] if "/" in postit_path else "")
                note_name = postit_path.rsplit("/", 1)[-1]
                sticky_notes.append({
                    "context": context,
                    "name": note_name,
                    "text": note_text,
                })

    # Extract network box labels (.netboxinit sections)
    netboxes = []
    for name, body in sections.items():
        if name.endswith(".netboxinit"):
            label = _parse_netbox_comment(body)
            if label:
                box_path = name[:-11]  # strip .netboxinit
                context = "/" + (box_path.rsplit("/", 1)[0] if "/" in box_path else "")
                box_name = box_path.rsplit("/", 1)[-1]
                netboxes.append({
                    "context": context,
                    "name": box_name,
                    "label": label,
                })

    return {
        "source": source,
        "nodes": list(nodes_by_path.values()),
        "connections": connections,
        "sticky_notes": sticky_notes,
        "netboxes": netboxes,
    }


def parse_hip_file(filepath):
    """Parse a .hip file into structured data.

    Returns:
        {
            "source": str,
            "nodes": [{"type", "path", "name", "category", "parameters",
                        "children", "comment"?}],
            "connections": [{"src_path", "src_output", "dst_path", "dst_input"}],
            "sticky_notes": [{"context", "name", "text"}],
            "netboxes": [{"context", "name", "label"}],
        }
    """
    with open(filepath, "rb") as f:
        data = f.read()
    return _build_result(_read_sections(data), str(filepath))


def parse_hip_bytes(data, source="<bytes>"):
    """Parse raw .hip bytes (for testing without files on disk)."""
    return _build_result(_read_sections(data), source)


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python hip_parser.py <file.hip>")
        sys.exit(1)

    result = parse_hip_file(sys.argv[1])
    print(json.dumps(result, indent=2))
