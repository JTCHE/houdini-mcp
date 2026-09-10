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

from bridge.cli import main  # noqa: E402


if __name__ == "__main__":
    main()
