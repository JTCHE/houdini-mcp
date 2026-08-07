# Houdini API

The `hou` module is the authority. Your memory of it is not.

Houdini changes method names, enum members, and node categories between
releases. Confirm a symbol exists before you call it: read the object with
`dir()`, or query the live session. Do not add a version check — the code must
run against the Houdini that the user has.

Do not record API facts in this repo. Facts about one release go stale. Use the
`docs` tool for reference, and the live session for truth.

## Failure behaviour

Houdini often fails without an error. A name that does not match, a parameter
with an expression, a node outside its frame range: each produces a wrong result
and no message.

So a handler must:

- Report what Houdini reported. Pass `node.errors()` and `node.warnings()` to
  the caller instead of a generic message.
- Name what it could not do. A parameter that does not exist, a node that did
  not cook, an input that it skipped — return it, do not drop it.
- Fail loudly on a partial result. Silence reads as success to the caller.
