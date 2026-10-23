#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON="${PYTHON_BIN}"
elif [[ -x "${SCRIPT_DIR}/.venv/bin/python" ]]; then
  PYTHON="${SCRIPT_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "Error: Python 3 not found on PATH" >&2
  exit 1
fi

EXE_PATH="${EXE_PATH:-}"
if [[ -z "${EXE_PATH}" ]]; then
  for candidate in \
    "${SCRIPT_DIR}/build/test_hpx" \
    "${SCRIPT_DIR}/build/Release/test_hpx"; do
    if [[ -x "${candidate}" ]]; then
      EXE_PATH="${candidate}"
      break
    fi
  done
fi

if [[ -z "${EXE_PATH}" || ! -x "${EXE_PATH}" ]]; then
  echo "Error: benchmark executable not found. Build test_hpx or set EXE_PATH." >&2
  exit 1
fi

exec "${PYTHON}" "${SCRIPT_DIR}/plot_thread_scatter.py" --exe "${EXE_PATH}" "$@"
