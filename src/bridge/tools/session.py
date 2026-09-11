"""session — is Houdini there, and start or stop one."""
import json

from ..connection import HoudiniError, call, start_gui, start_headless, status, stop_headless


def tool(action: str = "status", hip: str = None) -> str:
    """Report the Houdini session, or start or stop one.

    Use it first when a tool says that Houdini is not reachable, and use it to
    learn the Houdini version before you use an API that changed between
    releases.

    Do not use it to read the scene: scene_overview does that.

    action:
        "status" — what the bridge sees: the port, the connection, the Houdini
                   version, the open .hip file, and whether a GUI is attached.
                   Starts nothing.
        "start"  — start a headless Houdini (hython) and wait for it to answer.
                   Does nothing when a Houdini already listens.
        "start_gui" — start Houdini with its window and wait for the plugin to
                   answer, up to 4 minutes. It opens the .hip file at `hip`
                   when you give one. It stays open when the bridge stops. Use
                   it when you need the viewport, and do not start Houdini
                   from a shell yourself: a shell can give it other prefs.
        "stop"   — stop the headless Houdini that this bridge started. A
                   Houdini that you started yourself, or with "start_gui", is
                   not touched.

    Returns JSON. On "status" the report says what to do next when nothing
    listens on the port.
    """
    report = status()
    if action == "start":
        report["action"] = start_headless()
    elif action == "start_gui":
        report["action"] = start_gui(hip)
    elif action == "stop":
        report["action"] = stop_headless()
    elif action != "status":
        return f"Unknown action '{action}'. Use 'status', 'start', 'start_gui' or 'stop'."

    if report["port_is_listening"]:
        try:
            report["houdini"] = call("session", {}, timeout=15)
        except HoudiniError as error:
            report["houdini"] = str(error)
    else:
        from ..connection import PORT, start_hint
        report["next_action"] = start_hint(PORT)
    return json.dumps(report, indent=2, default=str)
