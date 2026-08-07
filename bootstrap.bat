@echo off
setlocal enabledelayedexpansion
REM bootstrap.bat — One-command setup for HoudiniMCP (Windows).
REM
REM Gets the repository and uv onto the machine, then hands over to the
REM installer, which does the Houdini plugin and the MCP client configuration.
REM
REM Fresh install:        powershell -c "irm https://raw.githubusercontent.com/JTCHE/houdini-mcp/main/bootstrap.bat -OutFile bootstrap.bat; .\bootstrap.bat"
REM From inside the repo: bootstrap.bat
REM No questions:         bootstrap.bat --yes
REM Every installer flag is passed through: bootstrap.bat --houdini-version 22.0 --harness codex

echo.
echo === HoudiniMCP bootstrap ===
echo.

where git >nul 2>&1
if errorlevel 1 (
    echo [FAIL] git is required. https://git-scm.com/download/win
    exit /b 1
)
for /f "tokens=*" %%v in ('git --version') do echo [OK]   %%v

set "PYTHON="
for %%c in (python3 python) do (
    if not defined PYTHON (
        %%c -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
        if !errorlevel! equ 0 set "PYTHON=%%c"
    )
)
if not defined PYTHON (
    echo [FAIL] Python 3.10+ is required. https://www.python.org/downloads/
    exit /b 1
)
for /f "tokens=*" %%v in ('!PYTHON! --version') do echo [OK]   %%v

if exist "pyproject.toml" if exist "houdini_mcp_server.py" set "IN_REPO=1"
if defined IN_REPO (
    echo [OK]   Already inside the repository
) else (
    echo [..]   Cloning houdini-mcp...
    git clone https://github.com/JTCHE/houdini-mcp.git || exit /b 1
    cd houdini-mcp
    echo [OK]   Cloned into !cd!
)

where uv >nul 2>&1
if errorlevel 1 (
    echo [..]   Installing uv...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;!PATH!"
)
where uv >nul 2>&1
if errorlevel 1 (
    echo [FAIL] uv install failed. https://docs.astral.sh/uv/
    exit /b 1
)
for /f "tokens=*" %%v in ('uv --version') do echo [OK]   %%v

uv run python scripts/onboarding/install.py %*
exit /b !errorlevel!
