# Deployment

This repo is the source. Houdini does not read it.

Houdini loads a **copy** of the plugin from its own preferences directory.
`src/bridge/onboarding/` makes that copy, as one Houdini package that holds the
module, the startup script and the shelf. An edit in `src/houdinimcp/` has no
effect on a running Houdini until you run the installer again and restart the
plugin.

The installer copies the `houdinimcp` package that it imports itself, so a clone
installs the working tree and a PyPI install installs the package. Run it from a
clone with `uv run python -m bridge.onboarding.install`.

The repository ships `.mcp.json`, a project-scope MCP server, for work inside
the repo. The installer writes a user-scope server as well, so a client that
reads both reports a scope conflict on the name `houdini`. Expected when you
install this repo onto itself; pick one scope to keep enabled.

Two copies that drift apart is the most costly failure in this project. If a fix
does not appear, confirm which copy Houdini loaded before you debug the code.
