"""Houdini-side TCP server that receives JSON commands from the MCP bridge."""
import select
import socket
import traceback

import hou

from . import protocol
from .tools import dispatch

EXTENSION_NAME = "Houdini MCP"
EXTENSION_VERSION = (0, 2)
EXTENSION_DESCRIPTION = "Connect Houdini to Claude via MCP"


class HoudiniMCPServer:
    def __init__(self, host='localhost', port=None):
        self.host = host
        self.port = port if port is not None else protocol.PORT
        self.running = False
        self.socket = None
        self.client = None
        self.buffer = b''
        # One object, so removeEventLoopCallback finds the callback it added.
        self._poll = self._process_server

    def start(self):
        """Listen on the port. In a GUI the Houdini event loop drives the poll.

        In hython there is no event loop, so the caller runs serve_forever.
        """
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            # Windows shares a bound port unless the first owner refuses it.
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.socket.bind((self.host, self.port))
        except OSError as error:
            self.socket.close()
            self.socket = None
            raise OSError(
                f"HoudiniMCP cannot listen on {self.host}:{self.port}: {error}. "
                f"Another process holds the port. Stop it, or set HOUDINIMCP_PORT "
                f"to a free port in Houdini and in the MCP client."
            ) from error
        self.socket.listen(1)
        self.socket.setblocking(False)
        self.running = True
        if hou.isUIAvailable():
            hou.ui.addEventLoopCallback(self._poll)
        print(f"HoudiniMCP server started on {self.host}:{self.port}")

    def serve_forever(self):
        """Drive the poll from this thread. For hython, which has no event loop."""
        while self.running:
            waiting = [sock for sock in (self.socket, self.client) if sock]
            select.select(waiting, [], [], 0.5)
            self._process_server()

    def stop(self):
        """Stop listening and close the sockets."""
        self.running = False
        if hou.isUIAvailable():
            hou.ui.removeEventLoopCallback(self._poll)
        self._drop_client()
        if self.socket:
            self.socket.close()
        self.socket = None
        print("HoudiniMCP server stopped")

    def _drop_client(self):
        if self.client:
            self.client.close()
        self.client = None
        self.buffer = b''

    def _process_server(self):
        """Accept a client and answer every complete frame it sent. Never blocks."""
        if not self.running:
            return
        try:
            if not self.client:
                try:
                    self.client, address = self.socket.accept()
                except BlockingIOError:
                    return
                self.client.setblocking(False)
                print(f"Connected to client: {address}")

            while True:
                try:
                    data = self.client.recv(protocol.CHUNK)
                except BlockingIOError:
                    break
                if not data:
                    print("Client disconnected")
                    self._drop_client()
                    return
                self.buffer += data

            commands, self.buffer = protocol.decode(self.buffer)
            for command in commands:
                response = protocol.encode(self.execute_command(command))
                self.client.setblocking(True)
                self.client.sendall(response)
                self.client.setblocking(False)
        except OSError as error:
            print(f"HoudiniMCP: connection lost: {error}")
            self._drop_client()

    def execute_command(self, command):
        """Run one tool and wrap the answer for the bridge."""
        try:
            result = dispatch(command.get("type", ""), command.get("params", {}))
            return {"status": "success", "result": result}
        except Exception as error:
            traceback.print_exc()
            return {"status": "error", "message": f"{type(error).__name__}: {error}"}
