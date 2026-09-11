"""The bridge side of the socket, and the headless Houdini it can start.

The MCP tools call `call()`. Nothing else in the bridge touches the socket.
"""
import json
import logging
import os
import platform
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from mcp.server.mcpserver.exceptions import ToolError

from houdinimcp import protocol

logger = logging.getLogger("HoudiniMCP.bridge")

PORT = protocol.PORT
HEADLESS_DISABLED = os.getenv("HOUDINIMCP_NO_HEADLESS", "").strip() in ("1", "true", "yes")
# hython runs this file by path, because it cannot import from the bridge venv.
HEADLESS_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(protocol.__file__)),
                               "headless.py")

_connection = None
_hython = None


class HoudiniError(ToolError):
    """Houdini could not be reached, or it refused the command.

    The message says what to do next. Show it to the user as it is.
    It is a ToolError because the MCP SDK hides the text of any other exception
    and sends only "Error executing tool <name>".
    """


@dataclass
class Connection:
    host: str
    port: int
    sock: socket.socket = None
    connected_since: float = None
    last_command_at: float = None
    command_count: int = 0

    def connect(self) -> bool:
        if self.sock is not None:
            return True
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=10)
            self.connected_since = time.monotonic()
            logger.info(f"Connected to Houdini at {self.host}:{self.port}")
            return True
        except OSError as error:
            logger.info(f"No Houdini on {self.host}:{self.port}: {error}")
            self.sock = None
            self.connected_since = None
            return False

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError as error:
                logger.error(f"Error closing the socket: {error}")
        self.sock = None
        self.connected_since = None

    def status(self) -> dict:
        return {
            "connected": self.sock is not None,
            "host": self.host,
            "port": self.port,
            "connected_since": self.connected_since,
            "last_command_at": self.last_command_at,
            "command_count": self.command_count,
        }

    def send(self, command: dict, timeout: float) -> dict:
        """Send one command and wait for its answer.

        A plugin restart kills the socket but not this object, so a lost
        connection is opened again once. The plugin that went away never read
        the command, so the second try cannot repeat work.
        """
        for attempt in (1, 2):
            if not self.connect():
                raise HoudiniError(start_hint(self.port))
            try:
                self.sock.settimeout(timeout)
                self.sock.sendall(protocol.encode(command))
                self.last_command_at = time.monotonic()
                self.command_count += 1
                return protocol.receive(self.sock)
            except socket.timeout:
                self.disconnect()
                raise HoudiniError(
                    f"Houdini did not answer '{command['type']}' in {timeout:.0f} seconds. "
                    f"A cook or a render can take longer. Look at the Houdini window, "
                    f"then call session with action='status'."
                )
            except OSError as error:
                self.disconnect()
                if attempt == 1:
                    logger.info(f"Connection lost ({error}); connecting again.")
                    continue
                raise HoudiniError(
                    f"The connection to Houdini failed on '{command['type']}': {error}. "
                    f"{start_hint(self.port)}"
                )


def start_hint(port: int) -> str:
    """What the user must do to get a Houdini that answers."""
    if HEADLESS_DISABLED:
        return (f"Nothing listens on port {port}, and HOUDINIMCP_NO_HEADLESS stops the "
                f"bridge from starting one. Start Houdini, or unset that variable.")
    if not find_hython():
        return (f"Nothing listens on port {port}, and no hython was found to start one. "
                f"Start Houdini, or set HFS to a Houdini install.")
    return (f"Nothing listens on port {port}. Start Houdini, or call session with "
            f"action='start' to run a headless one.")


def find_hython() -> Optional[str]:
    """Locate the hython binary, Houdini's Python interpreter."""
    hfs = os.environ.get("HFS")
    if hfs:
        for name in ("hython", "hython.exe"):
            candidate = os.path.join(hfs, "bin", name)
            if os.path.isfile(candidate):
                return candidate
    on_path = shutil.which("hython")
    if on_path:
        return on_path

    system = platform.system()
    roots = []
    if system == "Windows":
        for base in (r"C:\Program Files\Side Effects Software",
                     r"C:\Program Files (x86)\Side Effects Software"):
            if os.path.isdir(base):
                roots += [os.path.join(base, entry, "bin", "hython.exe")
                          for entry in sorted(os.listdir(base), reverse=True)]
    elif system == "Darwin":
        base = "/Applications/Houdini"
        if os.path.isdir(base):
            roots += [os.path.join(base, entry, "Frameworks", "Houdini.framework",
                                   "Versions", "Current", "Resources", "bin", "hython")
                      for entry in sorted(os.listdir(base), reverse=True)]
    if os.path.isdir("/opt"):
        roots += [os.path.join("/opt", entry, "bin", "hython")
                  for entry in sorted(os.listdir("/opt"), reverse=True) if entry.startswith("hfs")]
    for candidate in roots:
        if os.path.isfile(candidate):
            return candidate
    return None


def port_is_listening(port: int = None, host: str = "localhost") -> bool:
    try:
        with socket.create_connection((host, port or PORT), timeout=1):
            return True
    except OSError:
        return False


def houdini_env() -> dict:
    """The environment of a Houdini that the bridge starts.

    On Windows it names the prefs directory of a Houdini started from the Start
    menu. Without that, a bridge started from a shell that sets HOME (Git Bash
    does) gives Houdini $HOME/houdiniX.Y: other prefs, no plugin, and a stray
    directory. Houdini puts the release in place of __HVER__.
    """
    from .onboarding.houdini import prefs_dir_for
    environment = os.environ.copy()
    environment["HOUDINIMCP_PORT"] = str(PORT)
    if os.name == "nt" and not environment.get("HOUDINI_USER_PREF_DIR"):
        environment["HOUDINI_USER_PREF_DIR"] = prefs_dir_for("__HVER__")
    return environment


def _wait_for_port(process: subprocess.Popen, wait_seconds: float) -> bool:
    """Wait until the port listens. False when the time runs out; raises when
    the process stops first."""
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read().decode(errors="replace")[-800:] if process.stdout else ""
            raise HoudiniError(f"Houdini stopped before it could listen:\n{output}")
        if port_is_listening():
            return True
        time.sleep(0.5)
    return False


def start_headless(wait_seconds: float = 90.0) -> str:
    """Start a headless Houdini and wait for it to listen. Returns what happened."""
    global _hython
    if port_is_listening():
        return "A Houdini already listens on the port."
    hython = find_hython()
    if not hython:
        raise HoudiniError("No hython was found. Set HFS to a Houdini install, or start "
                           "Houdini yourself.")
    _hython = subprocess.Popen([hython, HEADLESS_SCRIPT], env=houdini_env(),
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        if _wait_for_port(_hython, wait_seconds):
            return f"Headless Houdini is ready on port {PORT}."
    except HoudiniError:
        _hython = None
        raise
    stop_headless()
    raise HoudiniError(f"hython did not listen within {wait_seconds:.0f} seconds. "
                       f"Houdini may want a license. Start Houdini yourself and try again.")


def start_gui(hip: str = None, wait_seconds: float = 240.0) -> str:
    """Start Houdini with its window, apart from the bridge, and wait for the
    plugin to listen. The bridge does not stop it. hip is a file to open."""
    if port_is_listening():
        return "A Houdini already listens on the port."
    hython = find_hython()
    houdini = hython and os.path.join(os.path.dirname(hython),
                                      "houdini.exe" if os.name == "nt" else "houdini")
    if not houdini or not os.path.isfile(houdini):
        raise HoudiniError("No Houdini was found. Set HFS to a Houdini install, or start "
                           "Houdini yourself.")
    if hip and not os.path.isfile(hip):
        raise HoudiniError(f"There is no file at {hip}.")
    detach = ({"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
              if os.name == "nt" else {"start_new_session": True})
    process = subprocess.Popen([houdini] + ([hip] if hip else []), env=houdini_env(),
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, **detach)
    if _wait_for_port(process, wait_seconds):
        return f"Houdini {houdini} is ready on port {PORT}."
    raise HoudiniError(f"Houdini started, but nothing listened on port {PORT} within "
                       f"{wait_seconds:.0f} seconds. It may still load, or want a license, "
                       f"or the plugin is not installed: run houdinimcp-install. Look at the "
                       f"window, then call session with action='status'.")


def stop_headless() -> str:
    """Stop the headless Houdini that this bridge started."""
    global _hython
    if not _hython or _hython.poll() is not None:
        _hython = None
        return "This bridge does not run a headless Houdini."
    _hython.terminate()
    try:
        _hython.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _hython.kill()
        _hython.wait()
    _hython = None
    return "The headless Houdini stopped."


def headless_is_ours() -> bool:
    return _hython is not None and _hython.poll() is None


def connection(auto_start: bool = True) -> Connection:
    """The one connection to Houdini. Starts a headless session if none listens."""
    global _connection
    if _connection is None:
        _connection = Connection(host="localhost", port=PORT)
    if _connection.sock is None and not port_is_listening() and auto_start \
            and not HEADLESS_DISABLED:
        start_headless()
    return _connection


def status() -> dict:
    """What the bridge knows about Houdini, without starting anything."""
    live = connection(auto_start=False)
    report = live.status()
    report["port_is_listening"] = port_is_listening()
    report["headless_started_by_bridge"] = headless_is_ours()
    report["hython"] = find_hython()
    return report


def call(command: str, params: Dict[str, Any] = None, timeout: float = 60.0) -> Any:
    """Run one command in Houdini and return its result.

    Raises HoudiniError with the next action in the message. Every tool uses
    this, so no tool has to know about the socket.
    """
    response = connection().send({"type": command, "params": params or {}}, timeout)
    if response.get("status") == "error":
        raise HoudiniError(f"Houdini refused '{command}': {response.get('message', 'no message')}")
    return response.get("result", {})


def call_json(command: str, params: Dict[str, Any] = None, timeout: float = 60.0) -> str:
    """`call`, as the JSON text that an MCP tool returns."""
    return json.dumps(call(command, params, timeout), indent=2, default=str)


def shutdown():
    """Close the socket and stop a headless Houdini that this bridge started."""
    global _connection
    if _connection is not None:
        _connection.disconnect()
        _connection = None
    stop_headless()
