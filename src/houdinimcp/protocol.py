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
import tempfile

# Without HOUDINIMCP_PORT the plugin lets the operating system pick a free port.
# A fixed number is not safe: Windows reserves blocks of ports for Hyper-V and
# WSL, and a bind in such a block fails with WinError 10013. The plugin writes
# the port it got to PORT_FILE, and the bridge reads it from there.
FORCED_PORT = int(os.environ["HOUDINIMCP_PORT"]) if os.environ.get("HOUDINIMCP_PORT") else None
# No user name from the environment: the bridge and Houdini must agree on this
# path, and a subprocess does not always carry USERNAME. On Windows the temporary
# directory is already per user; on POSIX the user id separates the files.
_SUFFIX = f"-{os.getuid()}" if hasattr(os, "getuid") else ""
PORT_FILE = os.path.join(tempfile.gettempdir(), f"houdinimcp{_SUFFIX}.port")

HEADER = struct.Struct(">I")
CHUNK = 1 << 20


def write_port(port) -> None:
    """Announce the port the plugin listens on. An empty value erases it."""
    with open(PORT_FILE, "w") as handle:
        handle.write(str(port))


def forget_port() -> None:
    """Erase the announced port, so a dead one does not look like a live Houdini."""
    write_port("")


def read_port():
    """The port Houdini listens on, or None when no Houdini announced one."""
    if FORCED_PORT:
        return FORCED_PORT
    try:
        with open(PORT_FILE) as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return None


def encode(message) -> bytes:
    """Make one frame from a JSON-serializable message."""
    body = json.dumps(message).encode("utf-8")
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
