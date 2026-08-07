"""Copy the plugin into a Houdini preferences directory and make Houdini load it.

Houdini reads a copy, never this repo. See agents/deployment.md.
"""
import json
import os
import shutil

PACKAGE_NAME = "houdinimcp"

PLUGIN_FILES = [
    "src/houdinimcp/__init__.py",
    "src/houdinimcp/server.py",
    "src/houdinimcp/HoudiniMCPRender.py",
    "src/houdinimcp/claude_terminal.py",
    "src/houdinimcp/event_collector.py",
]
HANDLER_DIR = "src/houdinimcp/handlers"
PANEL_FILES = ["src/houdinimcp/ClaudeTerminal.pypanel"]
SHELF_FILES = ["src/houdinimcp/houdinimcp.shelf"]

AUTOSTART_LINE = "import houdinimcp  # Auto-start HoudiniMCP server"


def _copy(source: str, destination: str, dry_run: bool, log: list) -> None:
    if not os.path.isfile(source):
        log.append(f"missing, skipped: {source}")
        return
    if not dry_run:
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(source, destination)
    log.append(f"{os.path.basename(source)} -> {destination}")


def install(prefs_dir: str, repo_dir: str, dry_run: bool = False) -> dict:
    """Install the plugin for one Houdini release. Returns what it wrote."""
    plugin_dest = os.path.join(prefs_dir, "scripts", "python", PACKAGE_NAME)
    log = []

    for relative in PLUGIN_FILES:
        _copy(os.path.join(repo_dir, relative),
              os.path.join(plugin_dest, os.path.basename(relative)), dry_run, log)

    handlers_source = os.path.join(repo_dir, HANDLER_DIR)
    handlers_dest = os.path.join(plugin_dest, "handlers")
    if os.path.isdir(handlers_source):
        if not dry_run:
            shutil.rmtree(handlers_dest, ignore_errors=True)
            shutil.copytree(handlers_source, handlers_dest)
        log.append(f"handlers/ -> {handlers_dest}")

    for relative in PANEL_FILES:
        _copy(os.path.join(repo_dir, relative),
              os.path.join(prefs_dir, "python_panels", os.path.basename(relative)), dry_run, log)
    for relative in SHELF_FILES:
        _copy(os.path.join(repo_dir, relative),
              os.path.join(prefs_dir, "toolbar", os.path.basename(relative)), dry_run, log)

    package_file = os.path.join(prefs_dir, "packages", f"{PACKAGE_NAME}.json")
    package = {
        "path": plugin_dest.replace("\\", "/"),
        "load_package_once": True,
        "version": "0.1",
        "env": [{"PYTHONPATH": {
            "value": os.path.join(prefs_dir, "scripts", "python").replace("\\", "/"),
            "method": "append",
        }}],
    }
    if not dry_run:
        os.makedirs(os.path.dirname(package_file), exist_ok=True)
        with open(package_file, "w", encoding="utf-8") as handle:
            json.dump(package, handle, indent=2)
            handle.write("\n")
    log.append(f"package -> {package_file}")

    # Claude Code launched from inside Houdini reads this to find the bridge.
    mcp_config = os.path.join(plugin_dest, "mcp.json")
    if not dry_run:
        os.makedirs(plugin_dest, exist_ok=True)
        with open(mcp_config, "w", encoding="utf-8") as handle:
            json.dump({"mcpServers": {"houdini": {
                "command": "uv",
                "args": ["--directory", repo_dir, "run", "python", "houdini_mcp_server.py"],
            }}}, handle, indent=2)
            handle.write("\n")
    log.append(f"mcp config -> {mcp_config}")

    pythonrc = os.path.join(prefs_dir, "scripts", "pythonrc.py")
    existing = ""
    if os.path.isfile(pythonrc):
        with open(pythonrc, encoding="utf-8") as handle:
            existing = handle.read()
    if "import houdinimcp" in existing:
        log.append(f"already starts on load: {pythonrc}")
    else:
        if not dry_run:
            os.makedirs(os.path.dirname(pythonrc), exist_ok=True)
            with open(pythonrc, "a", encoding="utf-8") as handle:
                if existing and not existing.endswith("\n"):
                    handle.write("\n")
                handle.write(AUTOSTART_LINE + "\n")
        log.append(f"auto-start -> {pythonrc}")

    return {"prefs_dir": prefs_dir, "plugin_dir": plugin_dest, "wrote": log}
