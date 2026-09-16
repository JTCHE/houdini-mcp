# Testing

Test your change. Do not commit the test.

Write the smallest check that fails if the logic breaks, run it, read the
result, then delete it. A test written for one change is waste in the tree: it
adds files to read, it goes stale, and nobody runs it again.

Keep a test only if the user asks for it, or if it protects logic that a person
cannot check by hand and that will change again.

Scratch scripts, smoke tests, and one-off harnesses go in a temporary directory,
never in the repo.

Prefer a real check over a mock. A Houdini behaviour is only confirmed against
a running Houdini or `hython`.

## Your own session, never the one the user has open

The user works in Houdini while you work on this server. A scene with hours of
simulation in it is not a test bed, and a plugin restart in that session throws
the work away.

Start your own:

- **Headless.** `session action='start'` starts a hython with the plugin, or run
  `src/houdinimcp/headless.py` with `hython` yourself. It announces itself like
  any other session, and `session action='list'` shows every one that runs.
- **With a window.** Start Houdini with `HOUDINI_USER_PREF_DIR` set to a
  directory of your own, and install the plugin into it with
  `--prefs-dir <that directory>`. The session of the user then keeps its own
  preferences, and yours cannot touch them.
- **Choose one.** `session action='attach'` with the port. Without it the bridge
  picks, and a command that lands in the wrong Houdini looks like a scene that
  lost its nodes. Every result carries `_session`: read it.

A viewport capture needs a window. Everything else answers in hython.
