# Deployment

This repo is the source. Houdini does not read it.

Houdini loads a **copy** of the plugin from its own preferences directory.
`scripts/install.py` makes that copy. An edit in `src/houdinimcp/` has no effect
on a running Houdini until you run the installer again and restart the plugin.

Two copies that drift apart is the most costly failure in this project. If a fix
does not appear, confirm which copy Houdini loaded before you debug the code.
