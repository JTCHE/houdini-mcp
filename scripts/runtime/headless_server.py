#!/usr/bin/env hython
"""
headless_server.py — Run the HoudiniMCP TCP server inside hython (no GUI).

Launched automatically by the MCP bridge when no Houdini instance is detected.
Can also be run manually:

    hython scripts/runtime/headless_server.py

Environment variables:
    HOUDINIMCP_PORT    TCP port (default: 9876)
"""
import sys
import os
import signal

# Add source directory to path so houdinimcp is importable from the repo
script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(os.path.dirname(script_dir), "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

try:
    from PySide6 import QtCore
except ImportError:
    from PySide2 import QtCore

# QCoreApplication is required for QTimer-based server polling
app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication(sys.argv)

# Handle SIGTERM gracefully so cleanup runs on bridge shutdown
signal.signal(signal.SIGTERM, lambda *_: app.quit())

# Skip __init__.py auto-start — we manage the server lifecycle here
os.environ["HOUDINIMCP_HEADLESS"] = "1"
from houdinimcp.server import HoudiniMCPServer

port = int(os.environ.get("HOUDINIMCP_PORT", 9876))
server = HoudiniMCPServer(port=port)
server.start()

print(f"Headless HoudiniMCP server ready on port {port}", flush=True)
sys.exit(app.exec())
