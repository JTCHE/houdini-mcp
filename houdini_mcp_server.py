#!/usr/bin/env python
"""The MCP bridge: it speaks MCP on stdin and stdout, and TCP to Houdini.

The tools live in src/bridge/tools, one module for each tool. Each module has a
mirror with the same name in src/houdinimcp/tools, which runs inside Houdini.
"""
import glob
import os
import sys
from contextlib import asynccontextmanager

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

for site_packages in (os.path.join(SCRIPT_DIR, ".venv", "Lib", "site-packages"),
                      *glob.glob(os.path.join(SCRIPT_DIR, ".venv", "lib",
                                              "python*", "site-packages"))):
    if os.path.exists(site_packages):
        sys.path.insert(0, site_packages)
        break

sys.path.insert(0, os.path.join(SCRIPT_DIR, "src"))
sys.path.insert(0, SCRIPT_DIR)

from mcp.server.mcpserver import MCPServer  # noqa: E402

from bridge import connection, tools  # noqa: E402

INSTRUCTIONS = """\
Houdini fails without an error more often than it fails with one. These five
facts cause most wrong results.

1. A parameter write has no effect when the parameter carries an expression or
   a keyframe. The write reports success. Read the value back.
2. A node name gets a numeric suffix when the name is already used. Keep the
   path that the create call returned. Do not look the node up by the name you
   asked for.
3. A cook error hides behind an empty geometry result. Read `node.errors()`.
4. The display flag and the render flag are different flags.
5. Inspect before you assume. Confirm a node type, a parameter name, a VEX
   function or a `hou` call with the `docs` tool or in the live session. Do not
   answer from memory about the Houdini API.
"""


@asynccontextmanager
async def lifespan(server):
    yield {}
    connection.shutdown()


def main():
    server = MCPServer("HoudiniMCP", instructions=INSTRUCTIONS, lifespan=lifespan)
    tools.register(server)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
