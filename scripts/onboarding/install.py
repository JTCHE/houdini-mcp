#!/usr/bin/env python3
"""
install.py — Set up HoudiniMCP: the Houdini plugin, the dependencies, and the
MCP client configuration of every agent harness you choose.

A person gets menus. An agent gets flags and JSON, and the same defaults:

    python scripts/onboarding/install.py                    # menus when a terminal is attached
    python scripts/onboarding/install.py --list             # what is on this machine, as JSON
    python scripts/onboarding/install.py --yes              # no questions, newest Houdini, every harness
    python scripts/onboarding/install.py --houdini-version 22.0 --harness claude-code --json
    python scripts/onboarding/install.py --dry-run          # report, change nothing

Without a terminal (a pipe, CI, an agent) the installer never blocks: it takes
the default for every question and says which default it took.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harnesses
import houdini
import plugin
import tui

REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Install HoudiniMCP: plugin, dependencies and MCP client configuration.",
    )
    parser.add_argument("--list", action="store_true",
                        help="Print the Houdini installs and harnesses found, as JSON, then exit")
    parser.add_argument("--houdini-version", default=None,
                        help="Release to install the plugin for, e.g. 22.0. 'none' skips the plugin")
    parser.add_argument("--prefs-dir", default=None,
                        help="Explicit Houdini preferences directory, instead of a release")
    parser.add_argument("--harness", action="append", default=[], metavar="KEY",
                        help=f"Harness to configure, repeatable: {', '.join(harnesses.BY_KEY)}, all, none")
    parser.add_argument("--claude-permissions", dest="claude_permissions",
                        action="store_true", default=None,
                        help="Pre-approve the Houdini tools in Claude Code")
    parser.add_argument("--no-claude-permissions", dest="claude_permissions", action="store_false",
                        help="Leave Claude Code permissions alone")
    parser.add_argument("--skip-deps", action="store_true", help="Do not run 'uv sync'")
    parser.add_argument("--yes", "-y", action="store_true", help="Take every default, ask nothing")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change, change nothing")
    parser.add_argument("--json", action="store_true", help="Print a JSON summary on stdout")
    return parser.parse_args()


def choose_houdini(args, installs, asking):
    """Return the prefs directory to install into, or None to skip the plugin."""
    if args.prefs_dir:
        return args.prefs_dir
    if args.houdini_version == "none":
        return None
    if args.houdini_version:
        match = [install for install in installs if install.release == args.houdini_version
                 or install.version == args.houdini_version]
        if match:
            return match[0].prefs_dir
        # A release that is not installed yet is still a valid target.
        return houdini.prefs_dir_for(args.houdini_version)
    if not installs:
        return None
    if not asking:
        return installs[0].prefs_dir

    options = [f"Houdini {install.version}  ->  {install.prefs_dir}" for install in installs]
    options.append("Skip the Houdini plugin")
    choice = tui.select("Install the plugin for which Houdini?", options)
    return None if choice == len(installs) else installs[choice].prefs_dir


def choose_harnesses(args, asking):
    """Return the harnesses to configure."""
    requested = [key.lower() for key in args.harness]
    if "none" in requested:
        return []
    if "all" in requested:
        return list(harnesses.HARNESSES)
    if requested:
        unknown = [key for key in requested if key not in harnesses.BY_KEY]
        if unknown:
            raise SystemExit(f"Unknown harness: {', '.join(unknown)}. "
                             f"Known: {', '.join(harnesses.BY_KEY)}, all, none")
        return [harnesses.BY_KEY[key] for key in requested]

    found = harnesses.detected()
    if not asking:
        return found
    options = [f"{harness.label}{'' if harness.installed else '  (not detected)'}"
               for harness in harnesses.HARNESSES]
    preselected = [index for index, harness in enumerate(harnesses.HARNESSES) if harness.installed]
    chosen = tui.multiselect("Configure which agent harnesses?", options, preselected)
    return [harnesses.HARNESSES[index] for index in chosen]


def sync_dependencies(dry_run):
    """Create the venv and install the dependencies with uv."""
    if not shutil.which("uv"):
        tui.warn("uv is not installed — skipping dependencies. See https://docs.astral.sh/uv/")
        return False
    if dry_run:
        tui.step("would run: uv sync")
        return True
    result = subprocess.run(["uv", "sync"], cwd=REPO_DIR, stdout=tui.stream)
    if result.returncode != 0:
        tui.fail("uv sync failed")
        return False
    tui.ok("Dependencies installed")
    return True


def main():
    args = parse_args()
    installs = houdini.find_installs()

    if args.list:
        print(json.dumps({
            "repo_dir": REPO_DIR,
            "houdini": [install.as_dict() for install in installs],
            "harnesses": [{"key": harness.key, "label": harness.label,
                           "detected": harness.installed} for harness in harnesses.HARNESSES],
            "uv": shutil.which("uv"),
        }, indent=2))
        return 0

    if args.json:
        # stdout carries the JSON report and nothing else.
        tui.stream = sys.stderr

    asking = tui.interactive() and not args.yes
    summary = {"repo_dir": REPO_DIR, "dry_run": args.dry_run,
               "plugin": None, "harnesses": [], "errors": []}

    tui.title("=== HoudiniMCP install ===")
    tui.say(f"  Repository: {REPO_DIR}")
    if not asking:
        tui.say("  No terminal or --yes given: taking the default for every question.")

    tui.title("Houdini")
    if installs:
        for install in installs:
            tui.ok(f"Found Houdini {install.version}")
    else:
        tui.warn("No Houdini install found — the plugin step needs one")

    prefs_dir = choose_houdini(args, installs, asking)

    tui.title("Agent harnesses")
    for harness in harnesses.HARNESSES:
        (tui.ok if harness.installed else tui.step)(
            f"{harness.label}: {'detected' if harness.installed else 'not detected'}")
    chosen = choose_harnesses(args, asking)

    claude_permissions = args.claude_permissions
    if claude_permissions is None:
        claude_permissions = (
            tui.confirm("Pre-approve the Houdini tools in Claude Code (no prompt per call)?", True)
            if asking and any(harness.key == "claude-code" for harness in chosen)
            else False
        )

    if not args.skip_deps:
        tui.title("Dependencies")
        sync_dependencies(args.dry_run)

    tui.title("Houdini plugin")
    if prefs_dir:
        match = next((install for install in installs if install.prefs_dir == prefs_dir), None)
        python_libs = houdini.python_libs(prefs_dir, match)
        if not python_libs:
            error = (f"cannot find the Python library directory of the Houdini that uses "
                     f"{prefs_dir}. Install that Houdini release, or start it once.")
            summary["errors"].append(f"plugin: {error}")
            tui.fail(f"Plugin install failed: {error}")
        else:
            try:
                summary["plugin"] = plugin.install(prefs_dir, REPO_DIR, python_libs, args.dry_run)
                for line in summary["plugin"]["wrote"]:
                    tui.step(line)
                tui.ok(f"Plugin installed into {prefs_dir}")
            except OSError as error:
                summary["errors"].append(f"plugin: {error}")
                tui.fail(f"Plugin install failed: {error}")
    else:
        tui.warn("Skipped — run again with --houdini-version once Houdini is installed")

    tui.title("MCP client configuration")
    if not chosen:
        tui.warn("No harness configured. Register the bridge yourself:")
        tui.say(f"    uv --directory {REPO_DIR} run python houdini_mcp_server.py")
    for harness in chosen:
        try:
            target = harness.configure(REPO_DIR, args.dry_run)
            summary["harnesses"].append({"key": harness.key, "target": target})
            tui.ok(f"{harness.label}: {target}")
        except (OSError, RuntimeError) as error:
            summary["errors"].append(f"{harness.key}: {error}")
            tui.fail(f"{harness.label}: {error}")

    if claude_permissions:
        added = harnesses.allow_claude_tools(args.dry_run)
        summary["claude_permissions_added"] = added
        tui.ok(f"Claude Code permissions: {'added ' + ', '.join(added) if added else 'already set'}")

    tui.title("Done")
    if summary["plugin"]:
        tui.say("  Restart Houdini. The plugin starts the TCP server when Houdini loads it.")
    if summary["errors"]:
        for error in summary["errors"]:
            tui.fail(error)
    if args.json:
        print(json.dumps(summary, indent=2))
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        tui.warn("Cancelled.")
        sys.exit(130)
