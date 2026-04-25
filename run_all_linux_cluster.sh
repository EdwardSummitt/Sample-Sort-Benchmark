#!/usr/bin/env bash
set -euo pipefail

# One-shot Linux workflow:
# 1) Ensure vcpkg exists and is bootstrapped
# 2) Configure + build test_hpx
# 3) Create/use Python venv and install requirements
# 4) Run benchmark sweep + 3D plot generation

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

log() {
  printf "\n[%s] %s\n" "$(date +"%H:%M:%S")" "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: required command not found: $1" >&2
    exit 1
  fi
}

if [[ -n "${MODULES_TO_LOAD:-}" ]] && command -v module >/dev/null 2>&1; then
  log "Loading environment modules: ${MODULES_TO_LOAD}"
  # shellcheck disable=SC2086
  module load ${MODULES_TO_LOAD}
fi

require_cmd git
require_cmd cmake

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON="${PYTHON_BIN}"
elif command -v python3.11 >/dev/null 2>&1; then
  PYTHON="python3.11"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON="python"
else
  echo "Error: Python 3.11+ not found on PATH" >&2
  exit 1
fi

log "Using Python: ${PYTHON}"

VCPKG_DIR="${VCPKG_DIR:-${SCRIPT_DIR}/vcpkg}"
BUILD_DIR="${BUILD_DIR:-${SCRIPT_DIR}/build}"
BUILD_TYPE="${BUILD_TYPE:-Release}"
BUILD_JOBS="${BUILD_JOBS:-$(nproc)}"

if [[ ! -d "${VCPKG_DIR}" ]]; then
  log "Cloning vcpkg into ${VCPKG_DIR}"
  git clone https://github.com/microsoft/vcpkg.git "${VCPKG_DIR}"
fi

if [[ ! -x "${VCPKG_DIR}/vcpkg" ]]; then
  log "Bootstrapping vcpkg"
  "${VCPKG_DIR}/bootstrap-vcpkg.sh"
fi

log "Configuring CMake"
cmake -S . -B "${BUILD_DIR}" \
  -DCMAKE_BUILD_TYPE="${BUILD_TYPE}" \
  -DCMAKE_TOOLCHAIN_FILE="${VCPKG_DIR}/scripts/buildsystems/vcpkg.cmake"

log "Building test_hpx (jobs=${BUILD_JOBS})"
cmake --build "${BUILD_DIR}" --config "${BUILD_TYPE}" -j "${BUILD_JOBS}"

EXE_PATH=""
for candidate in \
  "${BUILD_DIR}/test_hpx" \
  "${BUILD_DIR}/${BUILD_TYPE}/test_hpx"; do
  if [[ -x "${candidate}" ]]; then
    EXE_PATH="${candidate}"
    break
  fi
done

if [[ -z "${EXE_PATH}" ]]; then
  echo "Error: built executable not found in ${BUILD_DIR}" >&2
  exit 1
fi

if [[ "${RECREATE_VENV:-0}" == "1" ]] && [[ -d .venv ]]; then
  log "Removing existing .venv because RECREATE_VENV=1"
  rm -rf .venv
fi

if [[ ! -d .venv ]]; then
  log "Creating Python virtual environment"
  "${PYTHON}" -m venv .venv
fi

log "Installing Python requirements"
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt

log "Running benchmark sweep and 3D plot generation"
./.venv/bin/python ./plot_thread_size_surface.py --exe "${EXE_PATH}" "$@"

log "Done. Outputs written in repo root:"
echo "  - benchmark_raw_trials.csv"
echo "  - benchmark_median_summary.csv"
echo "  - benchmark_3d_surface.png"
