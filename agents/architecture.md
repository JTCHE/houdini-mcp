# Architecture

Three layers. Each runs in a different process.

1. **Bridge** — `houdini_mcp_server.py` and `src/bridge/`. Speaks MCP over stdio
   to the client, and JSON over a TCP socket to the plugin. `connection.py` is
   the only place that touches the socket, and it starts a headless Houdini when
   nothing listens. `tools/` holds one module for each tool.
2. **Plugin** — `src/houdinimcp/`. Runs inside Houdini. `server.py` accepts the
   socket, `tools/` holds one module for each tool, and the tools call
   `handlers/`. Only this layer imports `hou`.
3. **Offline** — `houdini_docs.py` and `scripts/`. No Houdini needed.
   `houdini_docs.py` reads the documentation from HoudiniMD over HTTP.
   `scripts/onboarding/` installs, `scripts/runtime/` starts a session.

`src/houdinimcp/protocol.py` holds the port and the wire format. Both sides
import it, so neither side can define its own port. A message is a 4-byte
big-endian length, then the UTF-8 JSON body.

## The tool surface

One tool covers one noun. A `mode` argument chooses the action, and every tool
takes one item or a list of items, so no tool has a batch twin.

A tool is a pair of modules with the same name: `src/bridge/tools/<name>.py`
holds `tool(...)`, whose docstring is what the model reads, and
`src/houdinimcp/tools/<name>.py` holds `run(...)`, which does the work inside
Houdini. Both sides find their modules by the file name, so a new tool needs no
registration and no dispatch table. `MUTATES = True` on the plugin module puts
the call in an undo group.

## Boundaries

- The plugin must not know about MCP. The bridge must not import `hou`.
- Each handler module owns one Houdini context (nodes, geometry, LOPs, COPs...).
  A new context gets a new module, not a longer existing one.
- Handlers take plain JSON and return plain JSON. Keep Houdini types inside.
- A failure names the next action. "Not connected" is not an answer; "start
  Houdini, or call session with action='start'" is.
