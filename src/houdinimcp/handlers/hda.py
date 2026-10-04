"""HDA management handlers."""
import hou


def hda_list(category=None):
    """List available HDA definitions, optionally filtered by category."""
    result = []
    for cat_name, cat in hou.nodeTypeCategories().items():
        if category and cat_name != category:
            continue
        for name, node_type in cat.nodeTypes().items():
            defn = node_type.definition()
            if defn:
                result.append({
                    "name": name,
                    "category": cat_name,
                    "label": node_type.description(),
                    "library": defn.libraryFilePath(),
                })
        if len(result) >= 200:
            break
    return {"count": len(result), "definitions": result}


def hda_get(node_type, category=None):
    """Get detailed info about an HDA definition."""
    nt = _find_node_type(node_type, category)
    defn = nt.definition()
    if not defn:
        raise ValueError(f"No HDA definition for: {node_type}")
    return {
        "name": nt.name(),
        "label": nt.description(),
        "category": nt.category().name(),
        "library": defn.libraryFilePath(),
        "version": defn.version(),
        "max_inputs": defn.maxNumInputs(),
        "help": defn.comment() or "",
        "sections": list(defn.sections().keys()),
    }


def hda_install(file_path):
    """Install an HDA file into the current Houdini session."""
    hou.hda.installFile(file_path)
    definitions = hou.hda.definitionsInFile(file_path)
    installed = []
    for defn in definitions:
        installed.append({
            "name": defn.nodeType().name(),
            "category": defn.nodeTypeCategory().name(),
            "label": defn.description(),
        })
    return {"installed": True, "file": file_path, "definitions": installed}


def uninstall_hda(file_path):
    """Uninstall an HDA file from the current session."""
    hou.hda.uninstallFile(file_path)
    return {"uninstalled": True, "file": file_path}


def reload_hda(file_path):
    """Reload all HDA definitions from a file."""
    definitions = hou.hda.definitionsInFile(file_path)
    for defn in definitions:
        defn.updateFromNode(defn.nodeType().instances()[0]) if defn.nodeType().instances() else None
    hou.hda.installFile(file_path, force_use_assets=True)
    return {"reloaded": True, "file": file_path, "count": len(definitions)}


def update_hda(node_path):
    """Update an HDA definition from its current node contents."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    defn = node.type().definition()
    if not defn:
        raise ValueError(f"No HDA definition for node: {node_path}")
    defn.updateFromNode(node)
    return {"updated": True, "path": node_path, "type": node.type().name()}


def get_hda_sections(node_type, category=None):
    """Get the section names of an HDA."""
    nt = _find_node_type(node_type, category)
    defn = nt.definition()
    if not defn:
        raise ValueError(f"No HDA definition for: {node_type}")
    return {"type": node_type, "sections": list(defn.sections().keys())}


def get_hda_section_content(node_type, section_name, category=None):
    """Get the content of a specific HDA section."""
    nt = _find_node_type(node_type, category)
    defn = nt.definition()
    if not defn:
        raise ValueError(f"No HDA definition for: {node_type}")
    sections = defn.sections()
    if section_name not in sections:
        raise ValueError(f"Section not found: {section_name}")
    content = sections[section_name].contents()
    return {"type": node_type, "section": section_name, "content": content}


def set_hda_section_content(node_type, section_name, content, category=None):
    """Set the content of a specific HDA section."""
    nt = _find_node_type(node_type, category)
    defn = nt.definition()
    if not defn:
        raise ValueError(f"No HDA definition for: {node_type}")
    sections = defn.sections()
    if section_name not in sections:
        defn.addSection(section_name, content)
    else:
        sections[section_name].setContents(content)
    return {"type": node_type, "section": section_name, "updated": True}


def _find_node_type(node_type, category=None):
    """Find a node type by name and optional category."""
    nt = None
    if category:
        cat = hou.nodeTypeCategories().get(category)
        if not cat:
            raise ValueError(f"Category not found: {category}")
        nt = cat.nodeTypes().get(node_type)
    else:
        for cat in hou.nodeTypeCategories().values():
            nt = cat.nodeTypes().get(node_type)
            if nt:
                break
    if not nt and "/" in node_type:
        # The full name, as nameWithCategory() gives it: "Sop/labs::edge_damage".
        # Looked up last: some names hold a "/", such as "Object/musclerig::..."
        # in the Sop category.
        nt = hou.nodeType(node_type)
    if not nt:
        raise ValueError(f"Node type not found: {node_type}")
    return nt


def hda_create(node_path, name, label, file_path):
    """Create an HDA from an existing node."""
    node = hou.node(node_path)
    if not node:
        raise ValueError(f"Node not found: {node_path}")
    hda_node = node.createDigitalAsset(
        name=name,
        hda_file_name=file_path,
        description=label,
    )
    return {"created": True, "path": hda_node.path(), "name": name, "file": file_path}
