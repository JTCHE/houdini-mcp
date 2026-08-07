# Architecture

Three layers. Each runs in a different process.

1. **Bridge** — `houdini_mcp_server.py`. Speaks MCP over stdio to the client.
   Speaks JSON over a TCP socket to the plugin. Holds the tool definitions.
2. **Plugin** — `src/houdinimcp/`. Runs inside Houdini. `server.py` accepts the
   socket and dispatches to `handlers/`. Only this layer imports `hou`.
3. **Offline** — `houdini_docs.py` and `scripts/`. No Houdini needed. Doc lookup,
   `.hip` parsing, install, ingest.

A tool that needs `hou` gets a wrapper in the bridge and a function in a handler
module. A tool that does not need `hou` stays in the bridge alone.

## Boundaries

- The plugin must not know about MCP. The bridge must not import `hou`.
- Each handler module owns one Houdini context (nodes, geometry, LOPs, COPs...).
  A new context gets a new module, not a longer existing one.
- Handlers take plain JSON and return plain JSON. Keep Houdini types inside.
