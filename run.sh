#!/usr/bin/env bash
# GhostRead launcher for Linux and macOS.
#
#   ./run.sh                  opens a file picker
#   ./run.sh path/to/book.pdf opens that file
#
# On the first run it builds a virtual environment in this folder.

set -e
cd "$(dirname "$0")"

PYEXE=".venv/bin/python"

if [ ! -x "$PYEXE" ]; then
    echo
    echo "  First run, setting up GhostRead."
    echo
    python3 -m venv .venv
    "$PYEXE" -m pip install --upgrade pip --quiet
    "$PYEXE" -m pip install -r requirements.txt --quiet
    echo "  Setup done."
    echo
fi

if ! "$PYEXE" -c "import tkinter" 2>/dev/null; then
    echo "  tkinter is missing. Install it first:"
    echo "    Debian/Ubuntu: sudo apt install python3-tk"
    echo "    Fedora:        sudo dnf install python3-tkinter"
    echo "    macOS:         brew install python-tk"
    exit 1
fi

exec "$PYEXE" -m ghostread "$@"
