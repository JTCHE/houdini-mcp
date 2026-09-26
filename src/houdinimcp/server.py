"""Houdini-side TCP server that receives JSON commands from the MCP bridge."""
import inspect
import os
import select
import socket
import time
import traceback

import hou

from . import protocol, watchdog
from .tools import dispatch

EXTENSION_NAME = "Houdini MCP"
EXTENSION_VERSION = (0, 2)
EXTENSION_DESCRIPTION = "Connect Houdini to Claude via MCP"

WAITING = object()   # a call that waits for the event loop; see _step


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
        # Every client with the bytes it sent that do not yet make a frame.
        # Several clients can hold a socket: a bridge, and a script that the
        # agent runs for a long job. Their calls run one after the other.
        self.clients = {}
        self.busy = False
        self.waiting = None   # the call that waits for the event loop
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
        self.socket.listen(8)
        self.port = self.socket.getsockname()[1]
        protocol.announce(self.port, identity())
        watchdog.start()
        self.socket.setblocking(False)
        self.running = True
        if hou.isUIAvailable():
            hou.ui.addEventLoopCallback(self._poll)
        print(f"HoudiniMCP server started on {self.host}:{self.port}")

    def serve_forever(self):
        """Drive the poll from this thread. For hython, which has no event loop."""
        while self.running:
            waiting = [self.socket, *self.clients]
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
        for client in list(self.clients):
            self._drop(client)
        if self.socket:
            self.socket.close()
        self.socket = None
        protocol.withdraw(self.port)
        print("HoudiniMCP server stopped")

    def _drop(self, client):
        self.clients.pop(client, None)
        try:
            client.close()
        except OSError:
            pass

    def _process_server(self):
        """Accept new clients and answer every complete frame they sent. Never
        blocks."""
        # A call that runs the event loop (hou.ui.waitUntil) runs this poll as
        # well: a second call must not start inside it.
        if not self.running or self.busy:
            return
        while True:
            try:
                client, address = self.socket.accept()
            except (BlockingIOError, OSError):
                break
            client.setblocking(False)
            self.clients[client] = b''
            print(f"Connected to client: {address}")
        if self.waiting:
            self._resume()
        for client in list(self.clients):
            if self.waiting:
                return
            try:
                self._answer(client)
            except OSError as error:
                print(f"HoudiniMCP: connection lost: {error}")
                self._drop(client)

    def _answer(self, client):
        while True:
            try:
                data = client.recv(protocol.CHUNK)
            except BlockingIOError:
                break
            if not data:
                print("Client disconnected")
                self._drop(client)
                return
            self.clients[client] += data
        commands, rest = protocol.decode(self.clients[client])
        self.clients[client] = rest
        for index, command in enumerate(commands):
            name = command.get("type", "")
            answer = self._run(name, lambda: dispatch(name, command.get("params", {})))
            if answer is None:
                # The call waits. The commands after it wait in the buffer.
                self.waiting["client"] = client
                self.clients[client] = b"".join(
                    protocol.encode(later) for later in commands[index + 1:]) + rest
                return
            self._send(client, name, answer)

    def _send(self, client, name, answer):
        if client not in self.clients:
            return  # the caller went away while its call waited
        try:
            response = protocol.encode(answer)
        except Exception as error:
            # A result that cannot be written must not stop the plugin.
            # Without this, one bad value ends the session and every later
            # call reports that Houdini is not running.
            traceback.print_exc()
            response = protocol.encode({
                "status": "error",
                "message": f"The result of '{name}' could not be sent: "
                           f"{type(error).__name__}: {error}"})
        client.setblocking(True)
        client.sendall(response)
        client.setblocking(False)

    def _run(self, name, work):
        """Run one step of a call, and wrap its answer for the bridge. None when
        the call waits.

        Every answer names the session that made it. The scene file can change
        between two calls, so the identity is read now, not at start.
        """
        watcher = watchdog.watch(name, self.port)
        self.busy = True
        try:
            with watcher:
                result = work()
                if inspect.isgenerator(result):
                    result = self._step(name, result)
            if result is WAITING:
                return None
            answer = {"status": "success", "result": result}
        except watchdog.Stopped as stopped:
            answer = {"status": "error",
                      "message": f"'{name}' was stopped because "
                                 f"{watcher.reason or str(stopped) or 'the watchdog stopped it'}. "
                                 f"What it changed before that stays in the scene; undo "
                                 f"reverts it."}
        except Exception as error:
            traceback.print_exc()
            answer = {"status": "error", "message": f"{type(error).__name__}: {error}"}
        finally:
            self.busy = False
        self.waiting = None
        answer["session"] = {**identity(), "port": self.port}
        return answer

    def _step(self, name, generator, stop=False):
        """Run a waiting call up to its next wait.

        Karma draws the viewport only while the event loop of Houdini runs, and
        a call holds that loop, also through hou.ui.waitUntil. So a tool that
        must let Houdini draw is a generator: each `yield (seconds, done)`
        ends this step, and the poll runs the next step when done() is true or
        the seconds pass. Other calls wait until it ends.
        """
        try:
            if stop:
                seconds, done = generator.throw(
                    watchdog.Stopped("the caller interrupted it while it waited"))
            else:
                seconds, done = next(generator)
        except StopIteration as end:
            return end.value
        self.waiting = {**(self.waiting or {}), "name": name, "generator": generator,
                        "until": time.monotonic() + float(seconds), "done": done}
        return WAITING

    def _resume(self):
        waiting = self.waiting
        stop = os.path.exists(protocol.interrupt_file(self.port))
        if not stop and time.monotonic() < waiting["until"]:
            try:
                if not (waiting["done"] and waiting["done"]()):
                    return
            except Exception:
                pass  # the next step reads the same state and says what is wrong
        answer = self._run(waiting["name"],
                           lambda: self._step(waiting["name"], waiting["generator"], stop))
        if answer is not None:
            self._send(waiting["client"], waiting["name"], answer)
