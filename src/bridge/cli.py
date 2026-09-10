"""The entry point: build the MCP server and run it on stdio."""
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer

from . import connection, tools

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


def build() -> MCPServer:
    server = MCPServer("HoudiniMCP", instructions=INSTRUCTIONS, lifespan=lifespan)
    tools.register(server)
    return server


def main():
    build().run(transport="stdio")
