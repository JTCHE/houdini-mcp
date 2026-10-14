"""Which Karma engine reads a render setting.

Karma XPU shows the Karma CPU quality controls and ignores them. The UI does not
tell: a Hide When rule hides only some of them. The list of the render settings
that XPU reads is in the help of the installed Houdini (solaris.zip,
karma_xpu.txt, section "Supported features and limitations"). It is read from
there at run time, so it follows the installed version.
"""
import functools
import os
import re
import zipfile

import hou

# Karma Render Settings LOP and the Karma ROP: the nodes that carry `engine`.
SETTINGS_TYPES = ("karmarendersettings", "karma")
DELEGATES = {"BRAY_HdKarma": "cpu", "BRAY_HdKarmaXPU": "xpu"}
# The folders whose settings the XPU list covers. Other folders (AOVs, image
# output, deep output) hold settings that both engines read.
XPU_SCOPE = ("Rendering / Sampling", "Rendering / Limits", "Advanced / Sampling / Secondary",
             "Advanced / Buckets")


def _key(label):
    return re.sub(r"\s*\(.*", "", label).strip().lower()


@functools.lru_cache(None)
def xpu_labels():
    """The labels of the render settings that Karma XPU reads, in lower case.
    Empty when the help of this Houdini is not installed."""
    path = os.path.join(hou.text.expandString("$HFS"), "houdini", "help", "solaris.zip")
    try:
        with zipfile.ZipFile(path) as archive:
            text = archive.read("karma_xpu.txt").decode("utf-8", "replace")
    except (OSError, KeyError, zipfile.BadZipFile):
        return frozenset()
    section = text.split("(features)", 1)[-1].split("\n== ", 1)[0]
    return frozenset(_key(item) for item in re.findall(r"^\s+\* (.+)$", section, re.M))


def is_settings(node):
    return node.type().name().split("::")[0] in SETTINGS_TYPES and node.parm("engine") is not None


def ignored(parm, engine=None):
    """Why the engine that renders does not read `parm`, or None.

    `engine` is "cpu" or "xpu"; without it, the `engine` of the node. Only the
    XPU list is known: a setting that CPU ignores has a Hide When rule.
    """
    node = parm.node()
    if not is_settings(node):
        return None
    engine = engine or node.evalParm("engine")
    if engine != "xpu":
        return None
    if not " / ".join(parm.containingFolders()).startswith(XPU_SCOPE):
        return None
    labels = xpu_labels()
    label = parm.parmTemplate().label()
    if not labels or _key(label) in labels:
        return None
    return (f"Karma XPU does not read '{label}': it is not in the XPU list of supported "
            f"render settings (help: Karma XPU, Supported features and limitations)")
