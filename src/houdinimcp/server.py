"""Houdini-side TCP server that receives JSON commands from the MCP bridge."""
import os
import select
import socket
import traceback

import hou

from . import protocol
from .tools import dispatch

EXTENSION_NAME = "Houdini MCP"
EXTENSION_VERSION = (0, 2)
EXTENSION_DESCRIPTION = "Connect Houdini to Claude via MCP"


def identity() -> dict:
    """Which Houdini this is. Every answer carries it, so a caller can never
    work in a session that it did not mean to reach."""
    return {
        "pid": os.getpid(),
        "version": hou.applicationVersionString(),
        "product": hou.applicationName(),
        "ui": hou.isUIAvailable(),
        "hip": hou.hipFile.path(),
    }


class HoudiniMCPServer:
    def __init__(self, host='localhost', port=None):
        self.host = host
        # 0 tells the operating system to pick a free port. See protocol.PORT_FILE.
        self.port = port if port is not None else (protocol.FORCED_PORT or 0)
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
                f"Another process holds the port, or Windows reserved it (WinError "
                f"10013: see `netsh interface ipv4 show excludedportrange protocol=tcp`). "
                f"Unset HOUDINIMCP_PORT to let the operating system pick a free port."
            ) from error
        self.socket.listen(1)
        self.port = self.socket.getsockname()[1]
        protocol.announce(self.port, identity())
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
            try:
                self._process_server()
            except Exception:
                # The loop must outlive one bad call. A plugin that stops here
                # reads to the caller as a Houdini that is not running.
                traceback.print_exc()

    def stop(self):
        """Stop listening and close the sockets."""
        self.running = False
        if hou.isUIAvailable():
            hou.ui.removeEventLoopCallback(self._poll)
        self._drop_client()
        if self.socket:
            self.socket.close()
        self.socket = None
        protocol.withdraw(self.port)
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
                try:
                    response = protocol.encode(self.execute_command(command))
                except Exception as error:
                    # A result that cannot be written must not stop the plugin.
                    # Without this, one bad value ends the session and every
                    # later call reports that Houdini is not running.
                    traceback.print_exc()
                    response = protocol.encode({
                        "status": "error",
                        "message": f"The result of '{command.get('type')}' could not be "
                                   f"sent: {type(error).__name__}: {error}"})
                self.client.setblocking(True)
                self.client.sendall(response)
                self.client.setblocking(False)
        except OSError as error:
            print(f"HoudiniMCP: connection lost: {error}")
            self._drop_client()

    def execute_command(self, command):
        """Run one tool and wrap the answer for the bridge.

        Every answer names the session that made it. The scene file can change
        between two calls, so the identity is read now, not at start.
        """
        try:
            result = dispatch(command.get("type", ""), command.get("params", {}))
            answer = {"status": "success", "result": result}
        except Exception as error:
            traceback.print_exc()
            answer = {"status": "error", "message": f"{type(error).__name__}: {error}"}
        answer["session"] = {**identity(), "port": self.port}
        return answer
