#!/usr/bin/env bash
# bootstrap.sh — One-command setup for HoudiniMCP (Linux + macOS).
#
# Gets the repository and uv onto the machine, then hands over to the
# installer, which does the Houdini plugin and the MCP client configuration.
#
# Fresh install:        curl -sSL https://raw.githubusercontent.com/JTCHE/houdini-mcp/main/bootstrap.sh | bash
# From inside the repo: bash bootstrap.sh
# No questions:         bash bootstrap.sh --yes
# Every installer flag is passed through: bash bootstrap.sh --houdini-version 22.0 --harness codex
set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC}   $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
warn() { echo -e "${YELLOW}[!!]${NC}   $1"; }
step() { echo -e "${CYAN}[..]${NC}   $1"; }

echo -e "\n${BOLD}=== HoudiniMCP bootstrap ===${NC}\n"

# Houdini sets PYTHONHOME/PYTHONPATH, which breaks every other Python process.
unset PYTHONHOME PYTHONPATH

command -v git >/dev/null || { fail "git is required. https://git-scm.com/downloads"; exit 1; }
ok "$(git --version)"

PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null &&
       "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done
[ -n "$PYTHON" ] || { fail "Python 3.10+ is required. https://www.python.org/downloads/"; exit 1; }
ok "$($PYTHON --version)"

if [ -f "pyproject.toml" ] && [ -f "houdini_mcp_server.py" ]; then
    ok "Already inside the repository"
else
    step "Cloning houdini-mcp..."
    git clone https://github.com/JTCHE/houdini-mcp.git
    cd houdini-mcp
    ok "Cloned into $(pwd)"
fi

if ! command -v uv >/dev/null; then
    step "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
command -v uv >/dev/null || { fail "uv install failed. https://docs.astral.sh/uv/"; exit 1; }
ok "$(uv --version)"

uv run python scripts/onboarding/install.py "$@"
