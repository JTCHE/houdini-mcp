# Mission

Read this before you add anything. It decides what belongs in this server and
what does not.

## The goal

Give an agent a small set of core tools that bend to any task, so that it can
work on its own inside a scene it has never seen. Two things make that
possible: the agent must be able to learn the state of the scene, and every
call must give back enough to decide what to do next.

## Few tools, many shapes

One tool is one generic purpose. A `mode` argument chooses the action, and the
other arguments bend the tool to the task.

- Never add a second tool for the batch form of an action. Every tool takes one
  item or a list of them.
- Never add a tool for one node type, one studio, one pipeline or one kind of
  shot. A tool that only a Pyro workflow can use is the wrong shape; the right
  shape is a tool that measures a volume, and Pyro is one thing it measures.
- Before you add a tool, look for the tool that should have grown a mode or an
  argument instead.
- When two tools do the same work with different names, join them.

The test for a request: **what is the general question behind it?** An agent
that asks for "a tool that tells me if my Pyro sim is dense enough" is asking
for "read the values of a volume". Build the general one.

## The right amount of context

Every result carries what the next decision needs, and nothing more.

- A call that changed nothing must say so, and say why. Houdini fails without
  an error more often than it fails with one.
- A read that gives back a whole dump is a read that costs a round trip in
  parsing. Give a filter and a shape.
- A result names the session that made it. An answer from the wrong Houdini
  reads as a scene that lost its nodes.

## Execute is the last resort

`execute` runs any Python in the session and is always there. It is not the
path an agent should take. Every hand-written script is a tool that is missing
a mode, and the feedback skill exists to catch that.

When you read a spec that says "I wrote this script twice", the answer is
almost never a new tool. It is an argument on a tool that is already there.

## The loop

An agent works in Houdini, then runs the feedback skill, which files specs in
the Obsidian base. Another agent reads the base and implements them. That is
the loop that makes this server better, and [Issues](issues.md) is how to work
in it.
