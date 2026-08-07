---
name: houdini-mcp-feedback
description: Short end-of-session survey about the Houdini MCP. Ask when the user says "feedback", "how did that feel", "survey", "houdini-mcp-feedback", or wants to know if the MCP tools felt efficient or if anything was missing.
---

# Houdini MCP feedback

Answer honestly and thoroughly based on this session's tool use (not regarding the actual Houdini work you produced) — the goal is surfacing your actual process: sequences of calls, places you had to improvise, and anywhere a human had to step in. Skip answering questions that don't apply because you didn't hit that situation. If your answer to one of them is "No issue", skip the question and move on to the next one. Don't skip if your answer takes a few bullets instead of one.

Questions:

1. Did you feel like your work leaned more efficient, or friction-y? Were there any tool calls you had to retry, work around, or where the way the results were formatted made you do extra parsing (full node dumps, geometry stats you had to slice yourself, verbose USD listings)?
2. What tools did you wish existed so you didn't have to fall back to `execute_houdini_code` / `execute_hscript`, or a multi-step workaround? Specifically call out any **generic, reusable primitive** you hand-wrote more than once in `execute_houdini_code` — e.g. walking a node network, finding a node by type/name/flag, resolving a parm's referencing expressions, listing every node downstream of X, checking cook errors across a subnet. Those are the ones worth turning into real tools; a one-off script built around this scene's own specific data doesn't count against the MCP.
3. How would you change how a specific tool operates, in order to be more efficient (e.g. more filter/field options so `get_node_info`, `get_scene_summary`, `list_children`, `get_points`/`get_attrib_values` return tailored results instead of a full dump)?
4. Did the `docs` tool earn its keep — did `query`/`page`/`node` get you the right HOM/VEX/parm signature, or did you still guess an API name and have it fail silently?
5. Did a connection error, plugin stall, or a slow render/cook bite you? Call out whether `batch` would have avoided it, whether the 1-second-between-calls rule cost you round-trips, and whether `monitor_render` / `get_render_progress` told you enough to avoid blind polling.
6. **Every point a human had to intervene** (approve a permission prompt, restart the Houdini MCP plugin, dismiss a Houdini dialog, save the scene, click something in the UI) — for each one: what triggered it, and what alternate sequence/ordering of tool calls on your end would have avoided needing them at all? Be concrete (e.g. "saved the scene defensively before the sim instead of after" / "batched node creation + connection + parm sets into one `batch` call instead of six round-trips"), not just "communicate better."
7. What state did you find yourself tracking manually across multiple tool calls (current network context, which nodes are dirty/uncooked, display vs render flag, current frame, take, whether a prior mutation left a network half-wired, sim cache validity) that the MCP could instead track or expose directly, so you don't have to infer it from a screenshot or a failed cook?
8. One thing you loved, that you wish to be kept exactly as-is.

Keep it tight per point (formatted like /i-have-adhd:i-have-adhd — lead with the concrete takeaway, no throat-clearing) but let questions 6-8 run to a few bullets each if the session actually had that much going on; don't compress real process insight down to one line just to hit a length target.
