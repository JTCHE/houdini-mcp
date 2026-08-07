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
