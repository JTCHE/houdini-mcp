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

HEADLESS_DISABLED = os.getenv("HOUDINIMCP_NO_HEADLESS", "").strip() in ("1", "true", "yes")
# hython runs this file by path, because it cannot import from the bridge venv.
HEADLESS_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(protocol.__file__)),
                               "headless.py")

_connection = None
_hython = None
# The port the caller chose with session action='attach'. Without one the bridge
# picks, and it refuses to pick when the choice is not obvious.
_attached_port = None
_last_session = None


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
        if not self.port:
            return False
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
                raise HoudiniError(start_hint())
            try:
                self.sock.settimeout(timeout)
                self.sock.sendall(protocol.encode(command))
                self.last_command_at = time.monotonic()
                self.command_count += 1
                return protocol.receive(self.sock)
            except socket.timeout:
                self.disconnect()
                raise HoudiniError(
                    f"Houdini on port {self.port} did not answer '{command['type']}' in "
                    f"{timeout:.0f} seconds. The work goes on: a timeout stops the wait, "
                    f"not the cook. Wait, then call session with action='status'. Do not "
                    f"start a second Houdini. Cook a long frame range in small parts, so "
                    f"that one call does not hold Houdini past the timeout."
                )
            except OSError as error:
                self.disconnect()
                if attempt == 1:
                    logger.info(f"Connection lost ({error}); connecting again.")
                    continue
                raise HoudiniError(
                    f"The connection to Houdini failed on '{command['type']}': {error}. "
                    f"{start_hint()}"
                )


def start_hint() -> str:
    """What the user must do to get a Houdini that answers.

    A Houdini that runs but does not accept is busy, not absent: a cook or a
    render holds the main thread, and the plugin cannot accept until it ends.
    To start a second Houdini then is the worst answer, so never say it.
    """
    busy = [entry for entry in live_sessions(probe=False) if process_is_alive(entry.get("pid"))]
    if busy:
        names = ", ".join(f"pid {entry.get('pid')} on port {entry['port']}"
                          f"{' (GUI)' if entry.get('ui') else ''}" for entry in busy)
        return (f"Houdini runs ({names}) and does not answer, so it is busy: a cook, a "
                f"simulation or a render holds it. Wait and call again. Do not start "
                f"another Houdini: a second one takes work and memory from this one.")
    if HEADLESS_DISABLED:
        return ("No Houdini listens for the bridge, and HOUDINIMCP_NO_HEADLESS stops the "
                "bridge from starting one. Start Houdini, or unset that variable.")
    if not find_hython():
        return ("No Houdini listens for the bridge, and no hython was found to start one. "
                "Start Houdini, or set HFS to a Houdini install.")
    return ("No Houdini listens for the bridge. Start Houdini, or call session with "
            "action='start' to run a headless one.")


def process_is_alive(pid) -> bool:
    """True when a process with this id runs. Used only to tell 'busy' from
    'gone', so a reused process id costs nothing."""
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        # SYNCHRONIZE alone: enough to open a live process, and it never asks
        # for rights that a normal user does not have.
        handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, int(pid))
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def live_sessions(probe: bool = True) -> list:
    """Every Houdini that announced itself, with the ones that answer marked.

    A Houdini that was killed leaves its file behind, so the port is the truth.
    `probe=False` skips the probe, for a message that must not wait.
    """
    found = []
    for entry in protocol.sessions():
        entry = dict(entry)
        if probe:
            # The plugin takes one client at a time, so the socket this bridge
            # already holds is proof, and a probe on it would be refused.
            live = _connection is not None and _connection.sock is not None \
                and _connection.port == entry["port"]
            entry["answers"] = live or port_is_listening(entry["port"])
        entry["running"] = process_is_alive(entry.get("pid"))
        if not entry["running"] and not entry.get("answers"):
            # A Houdini that was killed cannot take its own file away. Nobody
            # else will, so the list would grow with dead sessions for ever.
            protocol.withdraw(entry["port"])
            continue
        found.append(entry)
    return found


def choose_session(candidates: list) -> dict:
    """The one session to talk to, from the ones that answer.

    One session is the answer. Several with exactly one graphical session means
    the user works in that one and the others are strays, so take it and say so.
    Several graphical sessions is a real choice, and only the caller can make
    it: it must name a port with session action='attach'.
    """
    if len(candidates) == 1:
        return candidates[0]
    with_ui = [entry for entry in candidates if entry.get("ui")]
    if len(with_ui) == 1:
        return with_ui[0]
    names = "; ".join(f"port {entry['port']}: Houdini {entry.get('version', '?')} "
                      f"{'with a window' if entry.get('ui') else 'headless'}, "
                      f"pid {entry.get('pid')}, file {entry.get('hip') or 'none'}"
                      for entry in candidates)
    raise HoudiniError(
        f"{len(candidates)} Houdini sessions listen, and the bridge must not guess "
        f"which one holds your work. {names}. Call session with action='attach' and "
        f"the port you want.")


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


def port_is_listening(port: int, host: str = "localhost") -> bool:
    """True when a plugin accepts a connection on this port."""
    if not port:
        return False
    try:
        with socket.create_connection((host, port), timeout=1):
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
    if os.name == "nt" and not environment.get("HOUDINI_USER_PREF_DIR"):
        environment["HOUDINI_USER_PREF_DIR"] = prefs_dir_for("__HVER__")
    return environment


def _wait_for_new_session(process: subprocess.Popen, known: set, wait_seconds: float):
    """Wait for a session that was not there before, and attach to it.

    A new Houdini must not take the place of one that already runs, so the wait
    looks for a port that is new, not for any port.
    """
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read().decode(errors="replace")[-800:] if process.stdout else ""
            raise HoudiniError(f"Houdini stopped before it could listen:\n{output}")
        for entry in protocol.sessions():
            if entry["port"] not in known and port_is_listening(entry["port"]):
                attach(entry["port"])
                return entry
        time.sleep(0.5)
    return None


def start_headless(wait_seconds: float = 90.0) -> str:
    """Start a headless Houdini and wait for it to listen.

    A Houdini that already runs is left alone: this adds a session, it does not
    replace one. The bridge then talks to the new one.
    """
    global _hython
    hython = find_hython()
    if not hython:
        raise HoudiniError("No hython was found. Set HFS to a Houdini install, or start "
                           "Houdini yourself.")
    known = {entry["port"] for entry in protocol.sessions()}
    _hython = subprocess.Popen([hython, HEADLESS_SCRIPT], env=houdini_env(),
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        started = _wait_for_new_session(_hython, known, wait_seconds)
    except HoudiniError:
        _hython = None
        raise
    if started:
        return (f"A headless Houdini {started.get('version', '')} is ready on port "
                f"{started['port']}, and this bridge now talks to it.")
    stop_headless()
    raise HoudiniError(f"hython did not listen within {wait_seconds:.0f} seconds. "
                       f"Houdini may want a license. Start Houdini yourself and try again.")


def start_gui(hip: str = None, wait_seconds: float = 240.0) -> str:
    """Start Houdini with its window, apart from the bridge, and wait for the
    plugin to listen. The bridge does not stop it. hip is a file to open."""
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
    known = {entry["port"] for entry in protocol.sessions()}
    # The first start with a new preferences directory opens the usage
    # statistics question and the Start Here window, both over the viewport.
    # This is a Houdini that the bridge starts, so the choice is the caller's,
    # not a change to what the user set.
    environment = {**houdini_env(), "HOUDINI_NO_START_PAGE_SPLASH": "1"}
    process = subprocess.Popen([houdini] + ([hip] if hip else []), env=environment,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, **detach)
    started = _wait_for_new_session(process, known, wait_seconds)
    if started:
        return (f"Houdini {started.get('version', '')} is ready on port {started['port']}, "
                f"and this bridge now talks to it.")
    raise HoudiniError(f"Houdini started, but it did not listen within "
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


def attach(port: int) -> dict:
    """Send every command from now on to the Houdini on this port."""
    global _attached_port
    if not port_is_listening(port):
        raise HoudiniError(f"No Houdini answers on port {port}. Call session with "
                           f"action='list' to see the sessions that do.")
    if _connection is not None and _connection.port != port:
        _connection.disconnect()
        _connection.port = port
    _attached_port = port
    return {"attached_port": port}


def connection(auto_start: bool = True) -> Connection:
    """The connection to the chosen Houdini. Starts a headless one if none listens."""
    global _connection
    if _connection is None:
        _connection = Connection(host="localhost", port=None)
    if _connection.sock is not None:
        return _connection

    if _attached_port:
        # A caller that chose a session must never be moved to another one in
        # silence: a command that lands in the wrong Houdini reads as a scene
        # that lost its work.
        if port_is_listening(_attached_port):
            _connection.port = _attached_port
            return _connection
        raise HoudiniError(
            f"The Houdini on port {_attached_port}, which this session is attached to, "
            f"stopped answering. Call session with action='list' to see the sessions that "
            f"are there, then action='attach' with the port you want.")

    answering = [entry for entry in live_sessions() if entry.get("answers")]
    if not answering:
        if auto_start and not HEADLESS_DISABLED:
            start_headless()  # attaches to the session it started
            answering = [entry for entry in live_sessions() if entry.get("answers")]
        if not answering:
            _connection.port = None
            return _connection

    _connection.port = choose_session(answering)["port"]
    return _connection


def status() -> dict:
    """What the bridge knows about Houdini, without starting anything."""
    live = connection(auto_start=False)
    report = live.status()
    # The plugin takes one client at a time, so a probe while the bridge holds the
    # socket can time out. A live socket is proof enough.
    report["port_is_listening"] = live.sock is not None or port_is_listening(live.port)
    report["headless_started_by_bridge"] = headless_is_ours()
    report["attached_port"] = _attached_port
    report["sessions"] = live_sessions()
    report["hython"] = find_hython()
    return report


def call(command: str, params: Dict[str, Any] = None, timeout: float = 60.0) -> Any:
    """Run one command in Houdini and return its result.

    Raises HoudiniError with the next action in the message. Every tool uses
    this, so no tool has to know about the socket.
    """
    global _last_session
    started = time.monotonic()
    response = connection().send({"type": command, "params": params or {}}, timeout)
    _last_session = {**response.get("session", {}), "seconds": round(time.monotonic() - started, 3)}
    if response.get("status") == "error":
        raise HoudiniError(f"Houdini refused '{command}' ({session_line()}): "
                           f"{response.get('message', 'no message')}")
    return response.get("result", {})


def session_line() -> str:
    """One line that names the Houdini which answered last.

    A result that does not say which session made it is the most costly failure
    of this bridge: the caller reads the empty scene of a stray session as a
    scene that lost its nodes.
    """
    if not _last_session:
        return "no Houdini has answered yet"
    return (f"Houdini {_last_session.get('version', '?')} "
            f"{'with a window' if _last_session.get('ui') else 'headless'}, "
            f"pid {_last_session.get('pid')}, port {_last_session.get('port')}, "
            f"file {_last_session.get('hip') or 'none'}")


def call_json(command: str, params: Dict[str, Any] = None, timeout: float = 60.0) -> str:
    """`call`, as the JSON text that an MCP tool returns, with the session that
    answered and the time it took."""
    result = call(command, params, timeout)
    if isinstance(result, dict):
        result = {**result, "_session": session_line(), "_seconds": _last_session["seconds"]}
    else:
        result = {"result": result, "_session": session_line(),
                  "_seconds": _last_session["seconds"]}
    return json.dumps(result, indent=2, default=str)


def shutdown():
    """Close the socket and stop a headless Houdini that this bridge started."""
    global _connection
    if _connection is not None:
        _connection.disconnect()
        _connection = None
    stop_headless()


def last_version() -> str:
    """The Houdini build that answered last, for example "21.0.829".

    The documentation must match the session the caller works in, and asking
    Houdini for its version on every documentation read would need Houdini for
    a read that does not otherwise touch it.
    """
    if _last_session:
        return _last_session.get("version")
    for session in protocol.sessions():
        if session.get("version"):
            return session["version"]
    return None
