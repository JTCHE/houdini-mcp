#!/usr/bin/env python
"""The MCP bridge, started from the repository.

It puts the repository on the path and hands over to `bridge.cli`. The tools
live in src/bridge/tools, one module for each tool. Each module has a mirror
with the same name in src/houdinimcp/tools, which runs inside Houdini.
"""
import glob
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

for site_packages in (os.path.join(SCRIPT_DIR, ".venv", "Lib", "site-packages"),
                      *glob.glob(os.path.join(SCRIPT_DIR, ".venv", "lib",
                                              "python*", "site-packages"))):
    if os.path.exists(site_packages):
        sys.path.insert(0, site_packages)
        break

sys.path.insert(0, os.path.join(SCRIPT_DIR, "src"))

try:
    from bridge.cli import main  # noqa: E402
except ImportError as error:  # pragma: no cover - the client shows only stderr
    # A client reports a bridge that cannot start as "Connection closed" and
    # says nothing else. The reason must be on stderr, where its log keeps it.
    sys.stderr.write(
        f"HoudiniMCP cannot start: {error}\n"
        f"A dependency is missing from {SCRIPT_DIR}. Run:\n"
        f"    uv --directory {SCRIPT_DIR} sync\n"
        f"The bridge starts with `uv run --frozen`, so it uses the lock file as\n"
        f"it is and a change to pyproject.toml cannot stop a working setup.\n")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
