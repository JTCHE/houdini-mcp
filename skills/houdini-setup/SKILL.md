---
name: houdini-setup
description: Install the HoudiniMCP plugin into Houdini, so that a Houdini with its window open answers the houdini MCP server. Use it when the user wants to connect the Houdini that they have open, when a tool says that no Houdini listens for the bridge, or when Houdini has no HoudiniMCP shelf.
---

# Set up Houdini for the houdini MCP server

The houdini MCP server can start a headless `hython` without setup. A Houdini
that the user opens must load the HoudiniMCP plugin from its preferences
directory. This skill installs that plugin.

1. Tell the user that the installer writes a Houdini package into the
   preferences directory of their newest Houdini, and get their approval.
2. Run the installer from the plugin. Set `UV_PROJECT_ENVIRONMENT` to
   `${CLAUDE_PLUGIN_DATA}/venv` for the command, then run:

   ```
   uv run --frozen --project "${CLAUDE_PLUGIN_ROOT}" python -m bridge.onboarding.install --harness none --skip-deps --no-claude-permissions --yes --json
   ```

   `--harness none` is necessary: this plugin already adds the MCP server to
   Claude, and a second entry with the same name causes a conflict. The other
   two flags stop a second `uv sync` and leave the Claude Code permissions
   alone. To choose a Houdini version, add `--houdini-version 21.0`. To see the
   Houdini installs first, run the same command with `--list` in place of
   `--yes --json`.
3. Read the JSON report. Tell the user which preferences directory changed.
4. Tell the user to restart Houdini. After the restart, the HoudiniMCP shelf
   is there, and the `session` tool finds the open Houdini.
