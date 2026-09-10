---
name: houdini-mcp-feedback
description: End-of-session review of the Houdini MCP tools, filed as specs in the Obsidian vault. Run it when the user says "feedback", "how did that feel", "survey", "houdini-mcp-feedback", or asks whether the MCP tools felt efficient or if anything was missing.
---

# Houdini MCP feedback

You used the Houdini MCP in this session. Report what the tools did to your
work, and file what you find. You are the user of this server: nobody else can
see the friction that you felt.

Judge the tools, not the Houdini work you produced.

## 1. Survey yourself

Answer only the questions that this session touched. An answer of "no problem"
is not an answer to write down: skip that question.

1. **Friction.** Which calls did you retry, work around, or parse by hand
   because the result held more than you asked for?
2. **Missing tools.** Which generic thing did you write in `execute` more than
   once — walking a network, finding a node by type or flag, reading the
   expressions that point at a parameter, collecting the cook errors under a
   subnet? A script built around this one scene does not count.
3. **Shape of a result.** Which tool would be better with a filter or a field
   list, instead of the full dump?
4. **Documentation.** Did `docs` give you the right signature, or did you guess
   an API name and watch it fail without a message?
5. **Silent failures.** Did a write report success and change nothing? Did an
   empty result hide a cook error? Name the tool and what it should have said.
6. **Human help.** Every point where a person had to act — a permission prompt,
   a plugin restart, a dialog in Houdini, a click. For each one: what started
   it, and which order of calls on your side would have avoided it.
7. **State you tracked yourself.** Which state did you carry between calls
   (current network, dirty nodes, display against render flag, frame, take,
   a half-wired network) that a tool could have told you?
8. **Keep this.** One thing that worked, that must not change.

Lead each point with the concrete finding. No throat-clearing.

## 2. File what you found

Read the vault path from `.env.obsidian` in the repository root, the line
`OBSIDIAN_VAULT_PATH = <path>`. That file is not in git, and the path must
never go into a file that is.

The specs live in `<vault>/side projects/Houdini/HoudiniMCP/`.

**With no vault path, or no such folder:** print the survey in the chat and
write nothing. Say that the vault path is missing.

**With the folder:**

1. Read the file names and the frontmatter of the specs that are there. A spec
   with `Status: Open` is live work.
2. For each finding, decide: does an open spec already cover it?
   - **Yes** — append one line to that spec: the date, and what this session
     adds. Do not rewrite the paragraph that is there.
   - **No** — write a new spec.
3. Never change `Status` yourself. Only the user closes a spec.

A new spec is one file, named as a short sentence that says the problem, for
example `Parameter Writes Report Success They Did Not Achieve.md`:

```markdown
---
Type: Issue
Area: Bridge
Status: Open
Priority: P2
---
One paragraph. What happens, where, and what the tool must do instead. Name the
file and the function. Write it in ASD-STE100 Simplified Technical English, in
normal prose, for a person who did not see this session.
```

`Type` is `Issue` or `Feature`. `Area` is `Bridge`, `Plugin`, `Docs`,
`Onboarding` or `Tools`. `Priority` is `P1` for a thing that gives a wrong
result without an error, `P2` for a thing that costs round trips, `P3` for
polish.

Then tell the user, in the chat, which specs you appended to and which you
made.
