"""Run code in the Houdini session: Python, HScript, or an expression."""
from . import unknown_mode
from ..handlers import code, vex

MUTATES = True

MODES = ("python", "hscript", "expression", "vex_check", "env")


def run(source=None, mode="python", language="hscript", name=None):
    if mode == "python":
        return code.execute_code(source, allow_dangerous=True)
    if mode == "hscript":
        return code.execute_hscript(source)
    if mode == "expression":
        return code.evaluate_expression(source, language)
    if mode == "vex_check":
        return vex.validate_vex(source)
    if mode == "env":
        return code.get_env_variable(name or source)
    raise unknown_mode(mode, MODES)
