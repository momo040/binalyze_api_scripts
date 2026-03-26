#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${1:-${REPO_ROOT}/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Error: ${PYTHON_BIN} is not installed or not on PATH." >&2
    exit 1
fi

if [[ -d "${VENV_DIR}" ]]; then
    echo "Reusing existing virtual environment at ${VENV_DIR}"
else
    echo "Creating virtual environment at ${VENV_DIR}"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

echo "Upgrading pip..."
"${VENV_DIR}/bin/python" -m pip install --upgrade pip

echo "Installing requirements..."
"${VENV_DIR}/bin/python" -m pip install -r "${REPO_ROOT}/requirements.txt"

cat <<EOF

Virtual environment is ready.

Activate it with:
  source "${VENV_DIR}/bin/activate"
EOF
