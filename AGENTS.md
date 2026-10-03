# AGENTS.md

Project information: @README.md

**Read [Mission](guides/mission.md) first.** It says what this server is for and
what shape a change must take. Every other rule here serves it.

## Guides

- [Mission](guides/mission.md) — few tools, many shapes; execute is the last resort.
- [Issues](guides/issues.md) — where the specs live, and how to work from them.
- [Architecture](guides/architecture.md) — the three layers, and which file owns what.
- [Deployment](guides/deployment.md) — this repo is canonical; Houdini reads copies.
- [Code](guides/code.md) — one source of truth, small modules, no legacy paths.
- [Testing](guides/testing.md) — test the change in your own session, do not commit the test.
- [Houdini API](guides/houdini-api.md) — the API is the authority, not your memory.

## Rules

- Use ASD-STE100 Simplified Technical English in all writing: replies, comments,
  commits, pull requests.
- Do not keep backward compatibility. Delete the old path. Do not add fallbacks,
  shims, or migrations.
- Do not write documentation that a person can get from the code. Write a short
  comment in the code instead.
- Do not record a fact that goes stale: tool counts, version numbers, file
  inventories, status tables, audit results. Point to the code that holds it.
- Do not add a file to this repo unless the product needs it. Scratch work goes
  in a temporary directory.
- Do not commit or publish SideFX content or any other copyrighted material.
  This includes help pages, images from the Houdini install, and test fixtures
  made from them. Make a fixture on the machine that runs the test.
- Look at the change in a live Houdini before you report it done. Code that
  imports is not a plugin that answers. See [Deployment](guides/deployment.md):
  Houdini runs a copy, so run the installer and restart the plugin first. Start
  your own session; never work in the Houdini the user has open.
- When a change answers a spec, append a dated line to it and set `Status: Closed`.
