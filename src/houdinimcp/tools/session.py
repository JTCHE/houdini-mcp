"""What this Houdini is: version, product, scene file, frame, UI."""
import hou

MUTATES = False


def _modal():
    """The modal window that is open in front of Houdini, if there is one.

    A dialog covers the viewport and takes every click, so a picture of the
    viewport is a picture of the dialog and a person must clear it. The first
    start of a Houdini with a new preferences directory always opens two.
    """
    if not hou.isUIAvailable():
        return None
    try:
        from hutil.Qt import QtWidgets
        application = QtWidgets.QApplication.instance()
        window = application and application.activeModalWidget()
    except Exception:
        return None
    if not window:
        return None
    return {"title": window.windowTitle() or type(window).__name__,
            "note": "A modal window is open in front of Houdini. It covers the "
                    "viewport and takes every click. A person must close it."}


def run(action="status"):
    server = getattr(hou.session, "houdinimcp_server", None)
    return {
        "modal_dialog": _modal(),
        "houdini_version": hou.applicationVersionString(),
        "product": hou.applicationName(),
        "ui_available": hou.isUIAvailable(),
        "hip_file": hou.hipFile.path(),
        "hip_has_changes": hou.hipFile.hasUnsavedChanges(),
        "frame": hou.frame(),
        "fps": hou.fps(),
        "port": server.port if server else None,
    }
