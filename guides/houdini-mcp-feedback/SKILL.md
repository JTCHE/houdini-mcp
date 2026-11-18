---
name: houdini-mcp-feedback
description: End-of-session review of the Houdini MCP tools, filed through the feedback tool. Run it when the user says "feedback", "how did that feel", "survey", "houdini-mcp-feedback", or asks whether the MCP tools felt efficient or if anything was missing.
---

# Houdini MCP feedback

You used the Houdini MCP in this session. Report what the tools did to your
work, and file what you find. You are the user of this server: nobody else can
see the friction that you felt.

Judge the tools, not the Houdini work you produced.

The server is built on one idea: few tools, each one bent by its arguments to
any task. A finding is worth more when it names the general shape behind it.
"Pyro needs a density check" is one workflow; "no tool reads the values of a
volume" is the tool that was missing. Write the second one.

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
8. **Execute against named tools.** Did you use `execute` where a named tool
   existed? Count the calls on each side. For each `execute` call that a named
   tool could have made: did you know that tool existed, did it lack a field or
   a mode that you needed, or did one script replace several calls?
9. **Keep this.** One thing that worked, that must not change.

Lead each point with the concrete finding. No throat-clearing.

## 2. File what you found

Call the `feedback` tool once for each finding. Its arguments are the fields
of the spec: title, kind, area, priority, tool_name, happened, expected,
proposed_fix. `priority` is `P1` for a wrong result without an error, `P2` for
a thing that costs round trips, `P3` for polish.

Before you call it, read the open specs in the folder that the tool reports,
or the open issues. When a spec already covers the finding, append one dated
line to that spec and do not call the tool. Never change `Status` yourself.

Write each field in ASD-STE100 Simplified Technical English for a person who
did not see this session. Name the tool, the file and the function if you know
them. Do not ask for a new tool when a mode or an argument on a tool that
exists would do.

When the tool returns a link, give the link to the user.

Then tell the user, in the chat, which specs you appended to and which you
made.
