# Houdini MCP

<img src="public/cover.png" alt="An illustration titled &quot;Houdini MCP&quot;, showing multiple agentic platforms connected to Houdini, symbolizing a link" />


  <a href="https://pypi.org/project/houdini-mcp-server/"><img src="https://img.shields.io/pypi/v/houdini-mcp-server?color=blue" alt="PyPI Version"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/JTCHE/houdini-mcp?color=blue" alt="License: MIT"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white" alt="Python 3.10+"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-compatible-green" alt="MCP Compatible"/></a>
  <a href="https://www.sidefx.com/"><img src="https://img.shields.io/badge/Houdini-22.0-orange" alt="Houdini 22.0"/></a>


Connect SideFX Houdini to Claude, Codex, Gemini, Cursor, opencode or pi.

This MCP provides **Full Markdown Documentation** and **Viewport Screenshots** support to your agents of choice, enabling strong feedback loops and autonomous workflows.

## Install

**Windows**

```powershell
powershell -c "irm https://raw.githubusercontent.com/JTCHE/houdini-mcp/main/bootstrap.bat -OutFile bootstrap.bat; .\bootstrap.bat"
```

**macOS / Linux**

```bash
curl -sSL https://raw.githubusercontent.com/JTCHE/houdini-mcp/main/bootstrap.sh | bash
```

**uv**

```bash
uv tool install houdini-mcp-server && houdinimcp-install
```

The installer adds the plugin to Houdini and the server to your AI clients of choice. Restart both.\
pi also needs `pi install npm:pi-mcp-adapter`.

## Tools

| | |
|---|---|
| **Read** | `scene_overview` `node_inspect` `geometry_inspect` `stage_inspect` `select` `console` |
| **Edit** | `node_edit` `parm_set` `connect` `hda` `batch` |
| **Run** | `cook` `render` `pdg` `playbar` `scene_file` |
| **See** | `capture`: the viewport, a camera, four views or a flipbook |
| **Code** | `execute`: Python, HScript, expressions, VEX check |
| **Docs** | `docs`: the Houdini documentation of your build, offline, from [houdinimd-docs](https://pypi.org/project/houdinimd-docs/) |
| **Session** | `session`: status; starts Houdini headless or with its window |

No Houdini open? The server starts a headless `hython`.

> **Warning:** `execute` runs any Python in Houdini. Save your work.

<details>
<summary><b>Troubleshooting</b></summary>

| Problem | Fix |
|---|---|
| Nothing listens on port 9877 | Start Houdini, or click **Toggle MCP Server** on the HoudiniMCP shelf. |
| No HoudiniMCP shelf | Restart Houdini. `houdinimcp-install --list` shows where the plugin went. |
| Houdini started from Git Bash has no plugin | Git Bash sets `HOME`. Set the user variable `HOUDINI_USER_PREF_DIR` to `%USERPROFILE%\Documents\houdini__HVER__`. |
| `capture` says there is no viewport | The session is headless. Call `session` with `action="start_gui"`. |
| Port 9877 is busy | Set `HOUDINIMCP_PORT`. |

</details>

<details>
<summary><b>For agents and scripts</b></summary>

Without a terminal, the installer asks nothing and takes the defaults.

```bash
houdinimcp-install --list          # Houdini installs and clients found, as JSON
houdinimcp-install --yes --json    # newest Houdini, every client found; JSON report
houdinimcp-install --houdini-version 22.0 --harness claude-code --yes
houdinimcp-install --dry-run --yes # change nothing
```

Flags: `--houdini-version none` skips the plugin, `--prefs-dir PATH` names the
prefs folder, `--harness none|all|KEY` (repeatable), `--quiet-start` stops the
first-launch dialogs. The bootstrap scripts pass every flag through.

Manual client setup: run `houdinimcp-bridge` with no arguments.
`claude mcp add --transport stdio houdini -- houdinimcp-bridge` for Claude Code.

From a clone: `uv run python -m bridge.onboarding.install`.

Layout: `src/houdinimcp/` is the plugin, a TCP server inside Houdini on
`localhost:9877`. `src/bridge/` is the MCP server and the installer. Messages
are JSON with a 4-byte length prefix. `HOUDINIMCP_NO_HEADLESS=1` stops the
headless start. Read [AGENTS.md](AGENTS.md) before you change code.

</details>

## Credits

Built on [blender-mcp](https://github.com/ahujasid/blender-mcp),
[capoomgit/houdini-mcp](https://github.com/capoomgit/houdini-mcp),
[eetumartola/houdini-mcp](https://github.com/eetumartola/houdini-mcp),
[Houdini21MCP](https://github.com/orrzxz/Houdini21MCP) and
[fxhoudinimcp](https://github.com/healkeiser/fxhoudinimcp). MIT licensed.

<sub>Not affiliated with SideFX. Houdini and SideFX are trademarks of SideFX Software Inc.</sub>
