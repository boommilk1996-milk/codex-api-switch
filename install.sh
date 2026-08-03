#!/usr/bin/env bash
# codex-api-switch one-shot installer
#
# Usage:
#   bash install.sh                 # install CLI into ~/.local/bin
#   bash install.sh --app           # also build the macOS desktop app
#   bash install.sh --prefix DIR    # install into a custom directory
#
# Requirements:
#   - Codex installed on this machine (~/.codex/config.toml exists)
#   - Python 3.9+ (3.11+ recommended; older versions need `pip3 install tomli`)

set -euo pipefail

INSTALL_DIR="${HOME}/.local/bin"
BUILD_APP=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --app) BUILD_APP=1 ;;
        --prefix)
            [[ $# -ge 2 ]] || { echo "--prefix needs a directory"; exit 2; }
            INSTALL_DIR="$2"
            shift
            ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1"; usage; exit 2 ;;
    esac
    shift
done

say() { printf '\033[1;36m[install]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

say "Installing codex-api-switch to $INSTALL_DIR"

# 1. source files present?
for f in codex-api-switch deepseek-models.json README.md; do
    [[ -f "$SCRIPT_DIR/$f" ]] || die "missing $f next to install.sh — run this from the repository root"
done

# 2. Python
command -v python3 >/dev/null 2>&1 || die "python3 not found — install Python 3.9+ first"
if python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    say "Python $(python3 --version | awk '{print $2}') detected (tomllib built-in)"
elif python3 -c 'import tomli' 2>/dev/null; then
    say "Python $(python3 --version | awk '{print $2}') detected with tomli installed"
else
    say "Python < 3.11 and tomli missing — installing tomli via pip3..."
    pip3 install --user tomli || die "pip3 install tomli failed — install Python 3.11+ or run pip3 install --user tomli"
fi

# 3. Codex present? (warning only)
if [[ ! -f "${HOME}/.codex/config.toml" ]]; then
    say "NOTE: ~/.codex/config.toml not found — Codex may not be installed yet."
    say "      This tool switches Codex's provider, so it needs Codex installed."
fi

# 4. install files
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/codex-api-switch" "$INSTALL_DIR/codex-api-switch"
cp "$SCRIPT_DIR/deepseek-models.json" "$INSTALL_DIR/deepseek-models.json"
chmod +x "$INSTALL_DIR/codex-api-switch"
say "Installed codex-api-switch and deepseek-models.json -> $INSTALL_DIR"

# 5. PATH check
case ":${PATH}:" in
    *":${INSTALL_DIR}:"*) ;;
    *)
        say "WARNING: $INSTALL_DIR is not in your PATH."
        case "$(uname -s)" in
            Darwin)
                say "Add it with:  echo 'export PATH=\"$INSTALL_DIR:\$PATH\"' >> ~/.zshrc"
                ;;
            *)
                say "Add it with:  echo 'export PATH=\"$INSTALL_DIR:\$PATH\"' >> ~/.bashrc"
                ;;
        esac
        ;;
esac

# 6. optional macOS desktop app
if [[ "$BUILD_APP" -eq 1 ]]; then
    command -v osacompile >/dev/null 2>&1 || die "--app requires macOS with osacompile"
    APP_DIR="${HOME}/Desktop/Codex API 切换.app"
    if [[ -d "$APP_DIR" ]]; then
        cp -R "$APP_DIR" "${APP_DIR}.bak-$(date +%Y%m%d%H%M%S)"
        say "Backed up existing app to ${APP_DIR}.bak-*"
    fi
    osacompile -l JavaScript -o "$APP_DIR" "$SCRIPT_DIR/Codex_API_切换.app.js"
    say "Built desktop app: $APP_DIR"
fi

say "Done!"
say "Try it now:  codex-api-switch status"
say "Switch to DeepSeek (after quitting Codex):  codex-api-switch deepseek --api-key 'sk-...'"
say "Full guide: $INSTALL_DIR/../README.md or the repository README"
