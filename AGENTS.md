# AGENTS.md

Project information: @README.md

## Guides

- [Architecture](agents/architecture.md) — the three layers, and which file owns what.
- [Deployment](agents/deployment.md) — this repo is canonical; Houdini reads copies.
- [Code](agents/code.md) — one source of truth, small modules, no legacy paths.
- [Testing](agents/testing.md) — test the change, do not commit the test.
- [Houdini API](agents/houdini-api.md) — the API is the authority, not your memory.
- [Issues](agents/issues.md) — where specs live.

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
