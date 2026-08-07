# Houdini MCP

<img src="public/cover.png" alt="An illustration titled &quot;Houdini MCP&quot;, showing multiple agentic platforms connected to Houdini, symbolizing a link" />

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/kleer001/houdini-mcp?color=blue" alt="License: MIT"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white" alt="Python 3.10+"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-compatible-green" alt="MCP Compatible"/></a>
  <a href="https://www.sidefx.com/"><img src="https://img.shields.io/badge/Houdini-22.0-orange" alt="Houdini 22.0"/></a>
</p>

---

Control **SideFX Houdini** from an AI client (Claude, ChatGPT Codex, Gemini) through the **Model Context Protocol**.

The bridge talks to Houdini's Python API over a local TCP socket.

 If no Houdini GUI is running, the bridge starts a
headless `hython` session, so you can work without the UI.

- **Node, geometry, parameter, render, USD, PDG, HDA, COP, CHOP and DOP tools** —
  the current list is the set of `@mcp.tool()` functions in
  [`houdini_mcp_server.py`](houdini_mcp_server.py).
- **Documentation search** — Houdini docs and patterns from your own install.
- **Event system** — Houdini pushes scene changes back to the client.

## Install

**Prerequisites:** git and Python 3.10+. Houdini is optional at setup time.

The script clones the repo, installs [uv](https://docs.astral.sh/uv/), creates a
venv, installs the Houdini plugin, and writes your MCP client config.

**Windows**

```powershell
powershell -c "irm https://raw.githubusercontent.com/kleer001/houdini-mcp/main/bootstrap.bat -OutFile bootstrap.bat; .\bootstrap.bat"
```

**Linux / macOS**

```bash
curl -sSL https://raw.githubusercontent.com/kleer001/houdini-mcp/main/bootstrap.sh | bash
```

<details>
<summary><strong>Manual setup</strong></summary>

```bash
# 1. Install the plugin into your Houdini preferences directory
python scripts/install.py            # --dry-run to preview, --houdini-version to pin

# 2. Install dependencies
uv sync

# 3. Register the bridge with your MCP client
claude mcp add --transport stdio houdini -- uv --directory /path/to/houdini-mcp run python houdini_mcp_server.py

# 4. Optional: fetch the offline documentation corpus (~1 GB)
python scripts/fetch_houdini_docs.py
```

For a client that reads a JSON config, point `command` at `uv` with
`args: ["--directory", "/path/to/houdini-mcp", "run", "python", "houdini_mcp_server.py"]`.

ChatGPT accepts remote MCP servers only. Serve the bridge over HTTP
(`fastmcp run houdini_mcp_server.py --transport http`) and expose it with a tunnel.

</details>

## How it works

```
MCP client ──stdio──> houdini_mcp_server.py ──TCP──> src/houdinimcp/ ──> hou API
                                            └─────> houdini_docs.py (no Houdini needed)

No Houdini running? The bridge starts hython -> scripts/headless_server.py
```

The installer also adds a **HoudiniMCP** shelf with a button that starts and
stops the TCP server.

Headless mode gives you every tool except the ones that need a UI: viewport,
screenshots and flipbooks. Set `HOUDINIMCP_NO_HEADLESS=1` to turn auto-launch off.

## Ingest pipeline

`scripts/ingest_hips.py` reads the example `.hip` files in your Houdini install,
extracts node graphs and parameter recipes, and indexes them next to the
documentation. Run `python scripts/ingest_hips.py all`, or a single stage —
`discover`, `parse`, `extract-hdas`, `extract`, `index`.

## Contributing

Read [AGENTS.md](AGENTS.md) before you change anything. It carries the working
rules and links to the short guides in [`agents/`](agents/).

## Acknowledgements

Built on the work of [blender-mcp](https://github.com/ahujasid/blender-mcp),
[capoomgit/houdini-mcp](https://github.com/capoomgit/houdini-mcp),
[eetumartola/houdini-mcp](https://github.com/eetumartola/houdini-mcp),
[Houdini21MCP](https://github.com/orrzxz/Houdini21MCP) and
[fxhoudinimcp](https://github.com/healkeiser/fxhoudinimcp).

MIT licensed.

---

<sub>HoudiniMCP is an independent community project. It is not affiliated with,
endorsed by, or sponsored by SideFX Software. Houdini and SideFX are trademarks
of SideFX Software Inc.</sub>
