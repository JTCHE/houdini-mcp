# Houdini MCP

<img src="public/cover.png" alt="An illustration titled &quot;Houdini MCP&quot;, showing multiple agentic platforms connected to Houdini, symbolizing a link" />

<p align="center" alt="HoudiniMCP Server Glama Badge">
  <a href="https://glama.ai/mcp/servers/JTCHE/houdini-mcp"><img src="https://glama.ai/mcp/servers/JTCHE/houdini-mcp/badges/card.svg">
  </a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/JTCHE/houdini-mcp?color=blue" alt="License: MIT"/></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white" alt="Python 3.10+"/></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-compatible-green" alt="MCP Compatible"/></a>
  <a href="https://www.sidefx.com/"><img src="https://img.shields.io/badge/Houdini-22.0-orange" alt="Houdini 22.0"/></a>
</p>
---

Control **SideFX Houdini** from an AI client (Claude, ChatGPT Codex, Gemini) through the **Model Context Protocol**.

The bridge talks to Houdini's Python API over a local TCP socket.

If no Houdini GUI is running, the bridge starts a
headless `hython` session, so you can work without the UI.

- **20 tools** — one for each noun: `scene_overview`, `node_inspect`,
  `geometry_inspect`, `stage_inspect`, `node_edit`, `parm_set`, `connect`,
  `cook`, `execute`, `render`, `capture`, `console`, `docs`, `playbar`,
  `scene_file`, `select`, `hda`, `pdg`, `session`, `batch`. A `mode` argument
  chooses the action, and every tool takes one item or a list. The modules are
  in [`src/bridge/tools/`](src/bridge/tools/).
- **Honest failures** — a write that Houdini silently ignored is reported as
  such, and every error names the next action.
- **Documentation** — the official Houdini docs, read live from
  [HoudiniMD](https://houdinimd.com).

## Install

**Prerequisites:** git and Python 3.10+. Houdini is optional at setup time.

The script clones the repo, installs [uv](https://docs.astral.sh/uv/), installs
the Houdini plugin, and registers the bridge with the agent harnesses you pick.

**Windows**

```powershell
powershell -c "irm https://raw.githubusercontent.com/JTCHE/houdini-mcp/main/bootstrap.bat -OutFile bootstrap.bat; .\bootstrap.bat"
```

**Linux / macOS**

```bash
curl -sSL https://raw.githubusercontent.com/JTCHE/houdini-mcp/main/bootstrap.sh | bash
```

At a terminal you get menus: which Houdini release to install for, which
harnesses to configure — Claude Code, Claude Desktop, Codex, Gemini CLI, Cursor.

Already have the repository? Skip the bootstrap script, it only clones and
installs uv. Run the installer directly from the repository root:
`uv run python scripts/onboarding/install.py`.

<details>
<summary><strong>Unattended install (agents, CI, scripted setup)</strong></summary>

The installer never blocks without a terminal: it takes the default for every
question and says so. Flags make each choice explicit, and `--json` reports what
it did.

```bash
# What is on this machine, as JSON: Houdini releases, harnesses, uv
uv run python scripts/onboarding/install.py --list

# Every default: newest Houdini, every detected harness
uv run python scripts/onboarding/install.py --yes

# Explicit, and report what changed
uv run python scripts/onboarding/install.py \
    --houdini-version 22.0 --harness claude-code --harness codex --yes --json

# Report only, change nothing
uv run python scripts/onboarding/install.py --dry-run --yes
```

`bootstrap.sh` and `bootstrap.bat` pass every flag through, so the one-line
install above works unattended too — `bash bootstrap.sh --yes` on Linux and
macOS, `.\bootstrap.bat --yes` on Windows.

Useful flags: `--houdini-version none` skips the plugin, `--prefs-dir` names the
Houdini preferences directory outright, `--harness none` leaves every client
alone, `--skip-deps` skips `uv sync`.

With `--json`, stdout carries the JSON report and nothing else — the progress
log goes to stderr. The report names every file written and every client
configured, so it is also the verification: read `plugin.wrote` and
`harnesses[].target` back, and check `errors` is empty. `claude mcp list` is the
independent check for Claude Code.

</details>

<details>
<summary><strong>Manual setup</strong></summary>

```bash
uv sync
uv run python scripts/onboarding/install.py --harness none   # plugin only
claude mcp add --transport stdio houdini -- uv --directory /path/to/houdini-mcp run python houdini_mcp_server.py
```

For a client that reads a JSON config, point `command` at `uv` with
`args: ["--directory", "/path/to/houdini-mcp", "run", "python", "houdini_mcp_server.py"]`.

ChatGPT accepts remote MCP servers only. The bridge speaks stdio, so put a
stdio-to-HTTP proxy in front of it and expose that with a tunnel.

</details>

## How it works

```
MCP client ──stdio──> houdini_mcp_server.py ──TCP──> src/houdinimcp/ ──> hou API
                                            └─────> houdini_docs.py ──HTTP──> houdinimd.com

No Houdini running? The bridge starts hython -> scripts/runtime/headless_server.py
```

`scripts/` holds `onboarding/` (install) and `runtime/` (headless session,
launch).

The installer also adds a **HoudiniMCP** shelf with a button that starts and
stops the TCP server.

Headless mode gives you every tool except the ones that need a UI: viewport,
screenshots and flipbooks. Set `HOUDINIMCP_NO_HEADLESS=1` to turn auto-launch off.

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
