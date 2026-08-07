"""Terminal interface primitives for the installer.

Arrow-key menus with no dependency. Every prompt has a default, so the same
code path runs unattended: `interactive()` is false when there is no terminal,
and the caller takes the default instead of asking.
"""
import os
import sys

_COLORS = {
    "cyan": "\033[0;36m",
    "green": "\033[0;32m",
    "yellow": "\033[0;33m",
    "red": "\033[0;31m",
    "bold": "\033[1m",
    "dim": "\033[2m",
}
_RESET = "\033[0m"


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        # Windows terminals need virtual terminal processing turned on.
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    return True


_USE_COLOR = _color_enabled()


def paint(text: str, color: str) -> str:
    return f"{_COLORS[color]}{text}{_RESET}" if _USE_COLOR else text


def interactive() -> bool:
    """Is there a person at a terminal to answer a prompt?"""
    return sys.stdin.isatty() and sys.stdout.isatty()


def title(text: str) -> None:
    print(f"\n{paint(text, 'bold')}")


def step(text: str) -> None:
    print(f"{paint('[..]', 'cyan')}   {text}")


def ok(text: str) -> None:
    print(f"{paint('[OK]', 'green')}   {text}")


def warn(text: str) -> None:
    print(f"{paint('[!!]', 'yellow')}   {text}")


def fail(text: str) -> None:
    print(f"{paint('[FAIL]', 'red')} {text}", file=sys.stderr)


def _read_key() -> str:
    """Return one keypress as 'up', 'down', 'enter', 'space', 'quit' or a character."""
    if os.name == "nt":
        import msvcrt

        char = msvcrt.getwch()
        if char in ("\x00", "\xe0"):
            return {"H": "up", "P": "down"}.get(msvcrt.getwch(), "")
        if char == "\r":
            return "enter"
        if char == " ":
            return "space"
        if char in ("\x03", "\x1b", "q"):
            return "quit"
        return char

    import termios
    import tty

    descriptor = sys.stdin.fileno()
    saved = termios.tcgetattr(descriptor)
    try:
        tty.setraw(descriptor)
        char = sys.stdin.read(1)
        if char == "\x1b":
            sequence = sys.stdin.read(2)
            return {"[A": "up", "[B": "down"}.get(sequence, "quit")
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, saved)
    if char in ("\r", "\n"):
        return "enter"
    if char == " ":
        return "space"
    if char in ("\x03", "q"):
        return "quit"
    return char


def _draw(heading: str, lines: list, hint: str) -> None:
    print(f"\n{paint(heading, 'bold')}")
    for line in lines:
        print(line)
    print(paint(hint, "dim"))


def _erase(line_count: int) -> None:
    sys.stdout.write(f"\033[{line_count}A\033[J" if _USE_COLOR else "\n")
    sys.stdout.flush()


def select(heading: str, options: list, default: int = 0) -> int:
    """Pick one option. Returns its index, or the default with no terminal."""
    if not interactive() or len(options) == 1:
        return default

    current = default
    height = len(options) + 3
    first = True
    while True:
        if not first:
            _erase(height)
        first = False
        lines = [
            paint(f"> {option}", "cyan") if index == current else f"  {option}"
            for index, option in enumerate(options)
        ]
        _draw(heading, lines, "  up/down to move, Enter to choose")
        key = _read_key()
        if key == "up":
            current = (current - 1) % len(options)
        elif key == "down":
            current = (current + 1) % len(options)
        elif key == "enter":
            return current
        elif key == "quit":
            raise KeyboardInterrupt


def multiselect(heading: str, options: list, selected: list) -> list:
    """Toggle several options. Returns the indexes that are on."""
    if not interactive() or not options:
        return list(selected)

    chosen = set(selected)
    current = 0
    height = len(options) + 3
    first = True
    while True:
        if not first:
            _erase(height)
        first = False
        lines = []
        for index, option in enumerate(options):
            mark = "[x]" if index in chosen else "[ ]"
            row = f"{mark} {option}"
            lines.append(paint(f"> {row}", "cyan") if index == current else f"  {row}")
        _draw(heading, lines, "  up/down to move, space to toggle, Enter to confirm")
        key = _read_key()
        if key == "up":
            current = (current - 1) % len(options)
        elif key == "down":
            current = (current + 1) % len(options)
        elif key == "space":
            chosen.symmetric_difference_update({current})
        elif key == "enter":
            return sorted(chosen)
        elif key == "quit":
            raise KeyboardInterrupt


def confirm(question: str, default: bool = True) -> bool:
    """Ask a yes/no question. Returns the default with no terminal."""
    if not interactive():
        return default
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{question} {suffix}: ").strip().lower()
    if not answer:
        return default
    return answer.startswith("y")
