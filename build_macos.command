#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"

if [[ "$(uname -s)" != Darwin ]]; then
    echo "Run this script on macOS."
    exit 1
fi
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Install Python 3 with Tkinter from https://www.python.org/downloads/macos/ first."
    exit 1
fi
if [[ ! -x .venv-build/bin/python ]]; then
    "$PYTHON_BIN" -m venv .venv-build
fi
BUILD_PYTHON="$PWD/.venv-build/bin/python"
"$BUILD_PYTHON" -c 'import tkinter' || {
    echo "This Python installation needs Tkinter. Install Python from python.org and recreate .venv-build."
    exit 1
}
"$BUILD_PYTHON" -m pip --disable-pip-version-check install 'PyInstaller>=6.20,<7'
"$BUILD_PYTHON" -m unittest -v
"$BUILD_PYTHON" -m PyInstaller --clean --noconfirm ipPicka.spec
printf '\nBuilt: %s/dist/ipPicka.app\n' "$PWD"
printf 'Open the app in Finder. macOS will request authorization when changing network settings.\n'
