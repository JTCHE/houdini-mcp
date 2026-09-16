# Issues

Issues and features live as specs in an Obsidian base, not in this repo. Agents
that used this server wrote them, one file for each finding.

**Vault:** the line `OBSIDIAN_VAULT_PATH` in `.env.obsidian` in the repository
root. That file is not in git, and the path must never go into a file that is.

**Folder:** `<vault>/side projects/Houdini/HoudiniMCP/`
**Base:** `HoudiniMCP — Fork.base` in that folder, which is the view of it.

Specs live under `specs/<Type>/<Status>/` in that folder (e.g.
`specs/Issue/Open/`, `specs/Feature/Closed/`), sorted there by the Advanced
Note Mover plugin. A `.md` file directly in the folder, next to the base, is
not a spec: it is either `HoudiniMCP — Mission Statement.md`, a base file, or
an undated feedback log with no `Type`/`Status` frontmatter.

## Spec format

Frontmatter: `Type` (Issue | Feature), `Area` (Bridge | Plugin | Docs |
Onboarding | Tools), `Status` (Open | Closed), `Priority` (P1 | P2 | P3).

Body: one short paragraph. Name the file and the behaviour. State the decision
to make. No code blocks, no steps, no history.

`P1` is a wrong result with no error. `P2` costs round trips. `P3` is polish.

## "Look at the base, implement"

That prompt is the whole brief. This is what it means.

1. Read [Mission](mission.md) first. It decides what shape the answer takes.
2. List the specs with `Status: Open`. Work P1 first, then P2, then P3.
3. For each one, ask what the general question behind it is. Most specs name
   one node type or one workflow because that is what the agent was doing at
   the time. Build the general tool, then confirm it answers the spec.
   A spec that can only be answered by a tool for one pipeline is a spec to
   answer with an argument on a tool that exists, or to leave and say why.
4. Group the specs that share a cause. Several specs about a write that reports
   success are one fix in one write path.
5. Test each change in a live Houdini before you call it done. Start your own
   session: never work in the Houdini the user has open. See
   [Testing](testing.md) and [Deployment](deployment.md).
6. When a change answers a spec, set `Status: Closed`.

A spec that turns out to be wrong, or that the mission rules out, gets the same
dated line saying that, and why. Say it in the chat as well.
