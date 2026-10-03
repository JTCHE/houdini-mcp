# Code

## One source of truth

Each value, shape, and rule lives in one place. Ports, paths, defaults, and
patterns get one definition that every caller imports. A value written twice
will drift.

If you find the same value in two files, that is a bug. Fix the duplication
before you fix the symptom.

## Small modules

Split by purpose, not by size. A module does one thing and says so in its name.
Shared logic goes in a module both callers import — never copied, never
re-implemented.

Orchestration goes in the entry points. One-purpose logic goes in focused
modules that the entry points call.

## Change discipline

- Fix the cause, not the symptom. Before you edit a function, find every caller.
  One guard in the shared function beats a guard in each caller.
- Choose the simplest code that meets the current requirement. Do not add
  configuration, indirection, or abstraction for a need that does not exist yet.
- Delete more than you add when you can.
- Use names that explain themselves. `positionX`, not `pX`.
- Write a comment only when the code cannot show the reason. Keep it to one or
  two lines, next to the code it explains.
