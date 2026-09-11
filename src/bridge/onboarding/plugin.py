"""Copy the plugin into a Houdini preferences directory and make Houdini load it.

Houdini reads a copy, never this repo. See agents/deployment.md.

The copy is one Houdini package: `<prefs>/houdinimcp/` holds the module, the
startup script and the shelf, and `<prefs>/packages/houdinimcp.json` puts that
directory on the Houdini path. Houdini runs `pythonX.Ylibs/uiready.py` from
every directory on that path, after the UI is ready. This is why the package
needs the name of Houdini's own Python library directory.
"""
import json
import os
import shutil

import houdinimcp

PACKAGE_NAME = "houdinimcp"

# The plugin is copied from the houdinimcp package that this installer imports,
# so a repository checkout and a wheel both install the code that runs here.
MODULE_DIR = os.path.dirname(os.path.abspath(houdinimcp.__file__))
SHELF_FILE = os.path.join(MODULE_DIR, "houdinimcp.shelf")

# Houdini runs this after the UI is ready, in a graphical session only.
UIREADY_SCRIPT = """\
import houdinimcp

houdinimcp.start_server()
"""


def install(prefs_dir: str, python_libs: str, dry_run: bool = False) -> dict:
    """Install the plugin for one Houdini release. Returns what it wrote.

    python_libs is the name of Houdini's Python library directory, for example
    "python3.13libs". houdini.python_libs() finds it.
    """
    package_dir = os.path.join(prefs_dir, PACKAGE_NAME)
    module_dest = os.path.join(package_dir, python_libs, PACKAGE_NAME)
    log = []

    if not dry_run:
        shutil.rmtree(module_dest, ignore_errors=True)
        shutil.copytree(
            MODULE_DIR, module_dest,
            ignore=shutil.ignore_patterns("__pycache__", "*.shelf"),
        )
    log.append(f"module -> {module_dest}")

    uiready = os.path.join(package_dir, python_libs, "uiready.py")
    shelf = os.path.join(package_dir, "toolbar", os.path.basename(SHELF_FILE))
    package_file = os.path.join(prefs_dir, "packages", f"{PACKAGE_NAME}.json")
    # hpath puts the package directory on the Houdini path. "path" is deprecated.
    package = {"hpath": package_dir.replace("\\", "/"), "load_package_once": True}

    if not dry_run:
        _write(uiready, UIREADY_SCRIPT)
        os.makedirs(os.path.dirname(shelf), exist_ok=True)
        shutil.copy2(SHELF_FILE, shelf)
        _write(package_file, json.dumps(package, indent=2) + "\n")
    log.append(f"start on load -> {uiready}")
    log.append(f"shelf -> {shelf}")
    log.append(f"package -> {package_file}")

    return {"prefs_dir": prefs_dir, "plugin_dir": module_dest, "wrote": log}


QUIET_START = "HOUDINI_NO_START_PAGE_SPLASH"


def quiet_start(prefs_dir: str, dry_run: bool = False) -> str:
    """Stop the usage statistics dialog and the Start Here window that a new
    prefs directory opens on the first launch. Both cover the viewport, so a
    capture shows them instead of the scene. Adds one line to houdini.env and
    keeps the rest of the file. Returns what it did."""
    env_file = os.path.join(prefs_dir, "houdini.env")
    text = ""
    if os.path.isfile(env_file):
        with open(env_file, encoding="utf-8", errors="replace", newline="") as handle:
            text = handle.read()
    if any(line.split("=")[0].strip() == QUIET_START for line in text.splitlines()):
        return f"quiet start -> {env_file} (already set)"
    if not dry_run:
        newline = "\r\n" if "\r\n" in text or (not text and os.name == "nt") else "\n"
        lead = "" if not text or text.endswith("\n") else newline
        os.makedirs(prefs_dir, exist_ok=True)
        with open(env_file, "a", encoding="utf-8", newline="") as handle:
            handle.write(f"{lead}{QUIET_START} = 1{newline}")
    return f"quiet start -> {env_file}"


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
