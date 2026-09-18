#!/usr/bin/env bash
# Run linters (ruff check + ruff format --check) over the repository.
set -euo pipefail
cd "$(dirname "$0")"

VENV_PY="${VENV_PY:-/home/tony/venvs/entity_processing_validation/bin/python}"

"$VENV_PY" -m ruff check .
"$VENV_PY" -m ruff format --check .
echo "Linters passed."
