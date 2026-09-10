#!/usr/bin/env hython
"""Run the HoudiniMCP TCP server inside hython (no GUI).

The MCP bridge starts this when no Houdini session listens. You can also run it
yourself:

    hython scripts/runtime/headless_server.py

Set HOUDINIMCP_PORT to change the port. See src/houdinimcp/protocol.py.
"""
import os
import sys

# The repo source, so houdinimcp is importable without an install.
repo_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src_dir = os.path.join(repo_dir, "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from houdinimcp.server import HoudiniMCPServer

server = HoudiniMCPServer()
server.start()
print(f"Headless HoudiniMCP server ready on port {server.port}", flush=True)
try:
    server.serve_forever()
except KeyboardInterrupt:
    server.stop()
