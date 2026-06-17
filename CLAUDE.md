# CLAUDE.md — houdini-mcp (canonical repo)

Concise working notes. Detailed dev guidance: see [DEVELOPMENT.md](DEVELOPMENT.md).

## Repo model: this is canonical; Houdini dirs are consumers
- **Edit + git + GitHub here:** `Desktop/programming-tingz/houdini-mcp`.
- **Consumers** (what Houdini actually loads) live under
  `Documents/houdini21.0/scripts/python/`:
  - `houdinimcp/` — the **GUI plugin** (Houdini auto-scans `scripts/python`).
  - `houdini-mcp/` — the **bridge** the MCP config currently runs (`~/.claude.json`
    → `mcpServers.houdinimcp`).
- **Source of truth:** plugin = `src/houdinimcp/`; bridge = `houdini_mcp_server.py`
  + `houdini_docs.py`.
- ⚠️ No install script yet — until it exists, edits here must be **manually copied**
  to the consumer dirs to take effect in a live Houdini. (This bit us last session:
  the two plugin copies silently diverged.)

## Status (last session)
Live-tested against a headless `hython`. All exercised tools pass.
Tally: 8 fixed / 5 gated / 2 new — see [TOOLS_AUDIT.md](TOOLS_AUDIT.md).

## Open — minor UX gaps (not yet fixed)
- **`get_attrib_values`** (`handlers/geometry.py`): flattens vec3 into bare floats;
  `count` is the float count, not point count. Add `tuple_size` / group components.
- **`get_geo_summary`** (`handlers/geometry.py`): raises generic
  "Node has no geometry" when the real cause is an upstream cook error.
  Surface `node.errors()` instead.
- **`set_parameters`** (`handlers/parameters.py`): silently ignores unknown parm
  names. Return a `not_found` list so typos surface.

## Open — recommended hardening
- **Plugin listen socket** (`src/houdinimcp/server.py`): drop `SO_REUSEADDR` /
  use `SO_EXCLUSIVEADDRUSE`. On Windows `SO_REUSEADDR` lets a stray `hython`
  **hijack** the port (9877) from the GUI plugin, then refuse connections while
  `netstat` still shows LISTENING.
- **Bridge** (`houdini_mcp_server.py`): auto-retry once on `WinError 10054` so a
  plugin restart is transparent (today the first call fails, the second recovers).
- Headless auto-launch (`_launch_headless_houdini`) is the hijack trigger; keep
  `HOUDINIMCP_NO_HEADLESS=1` for GUI workflows (already set in `~/.claude.json`).

## Next steps
1. Build **install script**: copy `src/houdinimcp/` → Houdini `scripts/python/houdinimcp/`,
   and deploy the bridge. Make the consumer dirs reproducible from this repo.
2. Repoint `~/.claude.json` `mcpServers.houdinimcp` at the installed/canonical bridge.
3. **Publish:** confirm repo name + visibility, then add the new GitHub repo as
   `origin` and rename the current `origin` (`kleer001/houdini-mcp`) to `upstream`.
   Push `main`.
