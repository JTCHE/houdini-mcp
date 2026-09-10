"""What this Houdini is: version, product, scene file, frame, UI."""
import hou

MUTATES = False


def run(action="status"):
    server = getattr(hou.session, "houdinimcp_server", None)
    return {
        "houdini_version": hou.applicationVersionString(),
        "product": hou.applicationName(),
        "ui_available": hou.isUIAvailable(),
        "hip_file": hou.hipFile.path(),
        "hip_has_changes": hou.hipFile.hasUnsavedChanges(),
        "frame": hou.frame(),
        "fps": hou.fps(),
        "port": server.port if server else None,
    }
