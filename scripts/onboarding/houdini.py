"""Find the Houdini installs and preference directories on this machine."""
import glob
import os
import platform
import re
import shutil


class Install:
    """One Houdini install: its version, its executable and its prefs directory."""

    def __init__(self, version, executable=None):
        self.version = version                      # e.g. "22.0.368"
        self.release = ".".join(version.split(".")[:2])  # e.g. "22.0"
        self.executable = executable
        self.prefs_dir = prefs_dir_for(self.release)

    def __repr__(self):
        return f"Install({self.version})"

    def as_dict(self):
        return {
            "version": self.version,
            "release": self.release,
            "executable": self.executable,
            "prefs_dir": self.prefs_dir,
            "prefs_dir_exists": os.path.isdir(self.prefs_dir),
        }


def _version_key(version: str):
    return tuple(int(part) for part in re.findall(r"\d+", version)) or (0,)


def prefs_dir_for(release: str) -> str:
    """The user preferences directory Houdini uses for a release, e.g. '22.0'.

    Houdini puts the directory under $HOME. On Windows $HOME is often not set,
    and then Houdini uses the Documents folder. Python's expanduser reads
    USERPROFILE first, so it cannot answer this.
    """
    explicit = os.environ.get("HOUDINI_USER_PREF_DIR")
    if explicit:
        return explicit
    home = os.environ.get("HOME")
    system = platform.system()
    if system == "Windows":
        base = home or os.path.join(os.path.expanduser("~"), "Documents")
        return os.path.join(base, f"houdini{release}")
    home = home or os.path.expanduser("~")
    if system == "Darwin":
        return os.path.join(home, "Library", "Preferences", "houdini", release)
    return os.path.join(home, f"houdini{release}")


def python_libs(prefs_dir: str, install=None) -> str | None:
    """The name of Houdini's Python library directory, e.g. 'python3.13libs'.

    Houdini runs a startup script from this directory only, and the name holds
    the Python release, which changes between Houdini releases. The install
    holds the true name; the preferences directory holds it after a first run.
    """
    roots = []
    if install and install.executable:
        hfs = os.path.dirname(os.path.dirname(install.executable))
        roots.append(os.path.join(hfs, "houdini"))
    roots.append(prefs_dir)
    for root in roots:
        found = sorted(glob.glob(os.path.join(root, "python3*libs")))
        if found:
            return os.path.basename(found[-1])
    return None


def _executable_name() -> str:
    return "houdini.exe" if platform.system() == "Windows" else "houdini"


def _install_roots() -> list:
    """Directories that hold one versioned Houdini install each."""
    system = platform.system()
    if system == "Windows":
        return [
            os.path.join(base, entry)
            for base in (r"C:\Program Files\Side Effects Software",
                         r"C:\Program Files (x86)\Side Effects Software")
            if os.path.isdir(base)
            for entry in os.listdir(base)
        ]
    roots = []
    if system == "Darwin":
        for base in ("/Applications/Houdini",):
            if os.path.isdir(base):
                roots += [os.path.join(base, entry) for entry in os.listdir(base)]
    roots += sorted(glob.glob("/opt/hfs*"))
    return roots


def _executable_in(root: str) -> str | None:
    candidates = [os.path.join(root, "bin", _executable_name())]
    if platform.system() == "Darwin":
        candidates.append(os.path.join(
            root, "Frameworks", "Houdini.framework", "Versions", "Current",
            "Resources", "bin", "houdini",
        ))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def find_installs() -> list:
    """Every Houdini install found on disk, newest first.

    A prefs directory with no install behind it still counts — the user may have
    moved the install, and the plugin belongs in the prefs directory either way.
    """
    found = {}
    for root in _install_roots():
        match = re.search(r"(\d+\.\d+(?:\.\d+)*)", os.path.basename(root))
        if not match:
            continue
        version = match.group(1)
        executable = _executable_in(root)
        if version not in found or (executable and not found[version].executable):
            found[version] = Install(version, executable)

    for prefs in glob.glob(prefs_dir_for("*")):
        match = re.search(r"(\d+\.\d+)$", prefs.replace("\\", "/"))
        if not match:
            continue
        release = match.group(1)
        if not any(install.release == release for install in found.values()):
            found[release] = Install(release)

    on_path = shutil.which("houdini") or shutil.which("hython")
    if on_path and not found:
        found["unknown"] = Install("0.0", on_path)

    return sorted(found.values(), key=lambda install: _version_key(install.version), reverse=True)
