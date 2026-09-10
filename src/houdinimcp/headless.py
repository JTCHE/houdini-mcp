#!/usr/bin/env hython
"""Run the HoudiniMCP TCP server inside hython (no GUI).

The MCP bridge starts this when no Houdini session listens. You can also run it
yourself:

    hython -m houdinimcp.headless

Set HOUDINIMCP_PORT to change the port. See src/houdinimcp/protocol.py.
"""
import os
import sys

# hython does not see the bridge venv, so the bridge starts this file by path.
# Put the directory that holds the package on the path, then import it.
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from houdinimcp.server import HoudiniMCPServer


def main():
    server = HoudiniMCPServer()
    server.start()
    print(f"Headless HoudiniMCP server ready on port {server.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
