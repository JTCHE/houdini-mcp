"""The wire protocol between the bridge and the plugin.

Both sides import this module, so it must not import `hou`: the bridge runs in
its own venv, outside Houdini.

A message is one frame: a 4-byte big-endian length, then a UTF-8 JSON body.
The length lets the reader find the end of a message. Without it, a large
payload or two queued messages break the parse.
"""
import json
import os
import struct
import sys

# Without HOUDINIMCP_PORT the plugin lets the operating system pick a free port.
# A fixed number is not safe: Windows reserves blocks of ports for Hyper-V and
# WSL, and a bind in such a block fails with WinError 10013.
FORCED_PORT = int(os.environ["HOUDINIMCP_PORT"]) if os.environ.get("HOUDINIMCP_PORT") else None


def data_dir() -> str:
    """The folder where HoudiniMCP keeps what outlives one call.

    Not the temporary directory. Houdini and the bridge are different
    processes, and they do not always get the same TEMP: a Houdini that a
    launcher or a service starts gets C:\\Windows\\Temp, and then the bridge
    looks for its session in another folder and reports that no Houdini runs.

    A Houdini started from a shelf or a launcher can also have almost no
    environment: no LOCALAPPDATA, and `expanduser` that gives back "~". So on
    Windows the registry answers when the environment does not, and the result
    is always an absolute path that both processes compute the same way.
    """
    explicit = os.environ.get("HOUDINIMCP_HOME")
    if explicit:
        return explicit
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or _windows_local_appdata()
        return os.path.join(base, "HoudiniMCP")
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "HoudiniMCP")
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(base, "houdinimcp")


def _windows_local_appdata() -> str:
    """The Local AppData folder of this user, asked of Windows itself.

    Windows answers whatever the environment of the process holds. The
    registry is no help on its own: it writes the path as
    `%USERPROFILE%\\AppData\\Local`, and a process without USERPROFILE cannot
    expand that.
    """
    try:
        import ctypes
        buffer = ctypes.create_unicode_buffer(260)
        # SHGetFolderPathW, CSIDL_LOCAL_APPDATA (0x1c), current user.
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x1C, None, 0, buffer) == 0:
            return buffer.value
    except Exception:
        pass
    home = os.path.expanduser("~")
    if home != "~":
        return os.path.join(home, "AppData", "Local")
    import tempfile
    return tempfile.gettempdir()


# Every Houdini that runs the plugin writes one file here, named by its port.
# Several Houdini sessions can listen at the same time, so the bridge needs the
# list, not one number. A file for each port needs no lock: one writer each.
SESSIONS_DIR = os.path.join(data_dir(), "sessions")

HEADER = struct.Struct(">I")
CHUNK = 1 << 20


def announce(port: int, facts: dict) -> None:
    """Write the session file for a listening plugin.

    facts say which Houdini this is: pid, ui, version, product. The bridge shows
    them, so a caller can tell two sessions apart before it sends a command.
    """
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    with open(_session_file(port), "w") as handle:
        json.dump({"port": port, **facts}, handle)


def withdraw(port: int) -> None:
    """Remove the session file of a plugin that stopped listening."""
    try:
        os.remove(_session_file(port))
    except OSError:
        pass


def sessions() -> list:
    """Every announced session, newest last. The caller must still probe the
    port: a Houdini that was killed leaves its file behind."""
    if FORCED_PORT:
        return [{"port": FORCED_PORT, "source": "HOUDINIMCP_PORT"}]
    found = []
    try:
        names = sorted(os.listdir(SESSIONS_DIR))
    except OSError:
        return []
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(SESSIONS_DIR, name)
        try:
            with open(path) as handle:
                entry = json.load(handle)
        except (OSError, ValueError):
            continue
        # A file that is not a session (a half-written one, or any other JSON
        # value) must not crash every tool: the SDK reports that crash as a
        # bare "Error executing tool <name>".
        if isinstance(entry, dict) and isinstance(entry.get("port"), int):
            found.append(entry)
    return found


def _session_file(port: int) -> str:
    return os.path.join(SESSIONS_DIR, f"{port}.json")


def interrupt_file(port: int) -> str:
    """The bridge writes this file to stop the call that runs on this port. The
    plugin cannot read the socket while a call holds its main thread."""
    return os.path.join(SESSIONS_DIR, f"{port}.interrupt")


def output_file(port: int) -> str:
    """What a running script has printed so far, for a caller that cannot wait
    for the answer."""
    return os.path.join(SESSIONS_DIR, f"{port}.out")


def encode(message) -> bytes:
    """Make one frame from a message.

    A Houdini value is often an enum or a vector, which JSON does not know.
    `default=str` writes it as its text instead of raising: a result that holds
    one such value must not stop the plugin from answering.
    """
    body = json.dumps(message, default=str).encode("utf-8")
    return HEADER.pack(len(body)) + body


def decode(buffer: bytes):
    """Take every complete frame off the front of buffer.

    Returns the messages and the bytes that are still incomplete.
    """
    messages = []
    while len(buffer) >= HEADER.size:
        (length,) = HEADER.unpack_from(buffer)
        end = HEADER.size + length
        if len(buffer) < end:
            break
        messages.append(json.loads(buffer[HEADER.size:end].decode("utf-8")))
        buffer = buffer[end:]
    return messages, buffer


def receive(sock):
    """Read one whole frame from a blocking socket."""
    (length,) = HEADER.unpack(_read_exactly(sock, HEADER.size))
    return json.loads(_read_exactly(sock, length).decode("utf-8"))


def _read_exactly(sock, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(min(size - len(data), CHUNK))
        if not chunk:
            raise ConnectionAbortedError("Houdini closed the connection")
        data += chunk
    return bytes(data)
