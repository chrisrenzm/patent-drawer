#!/usr/bin/env bash
# First-run setup: a private Python environment next to the skill.
set -e
cd "$(dirname "$0")/.."
PY=$(command -v python3.12 || command -v python3)
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -c "import rdkit, pymupdf, openpyxl, olefile; print('patent-drawer: environment ready')"
