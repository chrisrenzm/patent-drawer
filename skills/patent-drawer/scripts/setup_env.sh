#!/usr/bin/env bash
# First-run setup: a private Python environment next to the skill.
set -e
cd "$(dirname "$0")/.."
PY=$(command -v python3.12 || command -v python3 || command -v python)
[ -d .venv ] || "$PY" -m venv .venv
# Windows puts the environment's programs in .venv/Scripts, macOS and Linux in .venv/bin.
BIN=.venv/bin; [ -d .venv/Scripts ] && BIN=.venv/Scripts
"$BIN/python" -m pip install -q -r requirements.txt
"$BIN/python" -c "import rdkit, pymupdf, openpyxl, olefile; print('patent-drawer: environment ready')"
