"""session — which Houdini answers, and start, choose or stop one."""
import json

from ..connection import (HoudiniError, attach, call, live_sessions, start_gui,
                          start_headless, status, stop_headless)


def tool(action: str = "status", hip: str = None, port: int = None) -> str:
    """Report the Houdini sessions, choose one, or start and stop one.

    Use it first when a tool says that Houdini is not reachable, and use it to
    learn the Houdini version before you use an API that changed between
    releases.

    Several Houdini sessions can listen at the same time: the graphical one that
    holds the work of the user, and a headless one for your own tests. Every
    tool result names the session that answered, in `_session`. Read that line
    when a scene looks empty or wrong: an empty scene is usually the wrong
    session, not a lost scene.

    Do not use it to read the scene: scene_overview does that.

    action:
        "status"    — the session that the bridge talks to now, the other
                      sessions, and the port. Starts nothing.
        "list"      — every Houdini that listens, with its version, its process
                      id, its .hip file, and whether it has a window.
        "attach"    — send every later command to the Houdini on `port`. Use it
                      when "list" shows more than one.
        "start"     — start a headless Houdini (hython) and attach to it. A
                      Houdini that already runs is not touched, so this is the
                      safe way to test while a person works in the window.
        "start_gui" — start Houdini with its window and wait for the plugin to
                      answer, up to 4 minutes. It opens the .hip file at `hip`
                      when you give one, it stays open when the bridge stops,
                      and the bridge attaches to it.
        "stop"      — stop the headless Houdini that this bridge started. A
                      Houdini that you started yourself, or with "start_gui", is
                      not touched.

    Returns JSON. On "status" the report says what to do next when nothing
    listens on the port.
    """
    if action == "list":
        return json.dumps({"sessions": live_sessions()}, indent=2, default=str)

    report = status()
    if action == "start":
        report["action"] = start_headless()
    elif action == "start_gui":
        report["action"] = start_gui(hip)
    elif action == "attach":
        if not port:
            return "action 'attach' needs a port. Call action='list' to see the ports."
        report["action"] = attach(port)
    elif action == "stop":
        report["action"] = stop_headless()
    elif action != "status":
        return (f"Unknown action '{action}'. Use 'status', 'list', 'attach', 'start', "
                f"'start_gui' or 'stop'.")

    if action in ("start", "start_gui", "attach"):
        report = {**report, **status()}
    if report["port_is_listening"]:
        try:
            report["houdini"] = call("session", {}, timeout=15)
        except HoudiniError as error:
            report["houdini"] = str(error)
    else:
        from ..connection import start_hint
        report["next_action"] = start_hint()
    return json.dumps(report, indent=2, default=str)
