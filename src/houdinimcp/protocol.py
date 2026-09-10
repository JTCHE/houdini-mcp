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

PORT = int(os.environ.get("HOUDINIMCP_PORT", "9877"))

HEADER = struct.Struct(">I")
CHUNK = 1 << 20


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
