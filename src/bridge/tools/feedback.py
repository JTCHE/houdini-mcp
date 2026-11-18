"""feedback — report a problem with these tools to the people who make them."""
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from mcp.types import ToolAnnotations

ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                              idempotentHint=False, openWorldHint=False)

ISSUES_URL = "https://github.com/JTCHE/houdini-mcp/issues/new"
# A longer URL can fail in the browser or the GitHub form.
MAX_URL_LENGTH = 8000
# Set on the maintainer's machine only: a folder that receives one spec per report.
DIRECTORY_VARIABLE = "HOUDINI_MCP_FEEDBACK_DIR"

KINDS = ("issue", "feature")
AREAS = ("Bridge", "Plugin", "Docs", "Onboarding", "Tools")
PRIORITIES = ("P1", "P2", "P3")

PARAMS = {
    "title": "A short sentence that says the problem, for example "
             "'Parameter writes report success they did not achieve'.",
    "kind": '"issue" for a thing that fails or costs round trips, "feature" for a thing that '
            "is missing.",
    "area": "Where the fix goes: Bridge, Plugin, Docs, Onboarding or Tools.",
    "priority": "P1: a wrong result with no error. P2: it costs round trips. P3: polish.",
    "tool_name": "The tool, and its mode if it has one, for example 'parm_set' or "
            "'geometry_inspect mode attributes'.",
    "happened": "What the tool did. Give the call and the result, cut to what matters.",
    "expected": "What the tool must do instead.",
    "proposed_fix": "The change you propose. Prefer a mode or an argument on a tool that exists "
                    "to a new tool.",
}


def tool(title: str, kind: str, area: str, priority: str, tool_name: str, happened: str,
         expected: str, proposed_fix: str) -> str:
    """Report one problem with these tools: a call that failed, a result you
    had to work around, a thing you wrote in execute because no tool did it.

    Use it when a tool costs you a retry or a script, at the time it happens or
    at the end of the work. Send one call for each problem. Judge the tools,
    not the Houdini work. Name the general shape behind the problem: "no tool
    reads the values of a volume", not "pyro needs a density check".

    Do not put the person's file paths, names, or scene content in the report.
    The tool replaces the home folder with "~", but it cannot find the rest.

    Returns a link to a GitHub issue that is filled in. Give the link to the
    person: they read the issue and submit it. When the server has a feedback
    folder, the tool writes the report there and returns the file path.
    """
    for name, value, allowed in (("kind", kind, KINDS), ("area", area, AREAS),
                                 ("priority", priority, PRIORITIES)):
        if value not in allowed:
            raise ValueError(f"{name} must be one of: {', '.join(allowed)}.")
    sections = (("Tool", tool_name), ("What happened", happened), ("Expected", expected),
                ("Proposed fix", proposed_fix))
    body = "\n\n".join(f"## {heading}\n\n{_scrubbed(text)}" for heading, text in sections)
    directory = os.environ.get(DIRECTORY_VARIABLE)
    if directory:
        return _written(Path(directory), _scrubbed(title), kind, area, priority, body)
    labels = f"feedback,{kind},{priority}"
    query = urlencode({"title": _scrubbed(title), "body": body, "labels": labels})
    url = f"{ISSUES_URL}?{query}"
    if len(url) > MAX_URL_LENGTH:
        raise ValueError(f"The report is too long for a link ({len(url)} characters, the limit "
                         f"is {MAX_URL_LENGTH}). Cut 'happened' to the lines that matter.")
    return f"Give this link to the person. They read the issue and submit it:\n{url}"


def _scrubbed(text: str) -> str:
    """The text with the home folder replaced by "~", in both slash styles."""
    home = str(Path.home())
    for form in {home, home.replace("\\", "/")}:
        text = re.sub(re.escape(form), "~", text, flags=re.IGNORECASE)
    return text


def _written(directory, title, kind, area, priority, body):
    """Write the report as one spec file in the feedback folder."""
    if not directory.is_dir():
        raise FileNotFoundError(f"{DIRECTORY_VARIABLE} names a folder that does not exist.")
    name = re.sub(r'[<>:"/\\|?*]', "", title).strip().rstrip(".")
    path = directory / f"{name}.md"
    if path.exists():
        raise FileExistsError(f"A spec with this title exists: {path}. Append to it instead.")
    front = (f"---\nType: {kind.title()}\nArea: {area}\nStatus: Open\nPriority: {priority}\n"
             f"Reported: {date.today().isoformat()}\n---\n")
    path.write_text(front + body + "\n", encoding="utf-8")
    return f"Wrote the spec: {path}"
