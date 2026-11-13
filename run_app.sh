#!/usr/bin/env bash
# NeuroSync launcher (Linux / macOS): venv -> dependencies -> models -> app
set -euo pipefail
cd "$(dirname "$0")"

VENV_DIR="${VENV_DIR:-.venv}"
PYTHON="${PYTHON:-python3}"

if [ ! -d "$VENV_DIR" ]; then
  echo "[setup] creating virtual environment in $VENV_DIR"
  "$PYTHON" -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip >/dev/null
pip install -r requirements.txt
python scripts/download_models.py

echo "[run] NeuroSync on http://127.0.0.1:8000  (API docs: http://127.0.0.1:8000/docs)"
exec python -m src.api
