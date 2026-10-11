#!/usr/bin/env bash
set -euo pipefail

# Focused Linux debug workflow for the 38-thread HPX case.
# This script is intentionally standalone: it does not modify or depend on
# debug-mode changes in plot_thread_size_surface.py.

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

VCPKG_DIR="${VCPKG_DIR:-${SCRIPT_DIR}/vcpkg}"
BUILD_DIR="${BUILD_DIR:-${SCRIPT_DIR}/build}"
BUILD_TYPE="${BUILD_TYPE:-Release}"
BUILD_JOBS="${BUILD_JOBS:-$(nproc)}"

if [[ ! -d "${VCPKG_DIR}" ]]; then
  require_cmd git
  log "Cloning vcpkg into ${VCPKG_DIR}"
  git clone https://github.com/microsoft/vcpkg.git "${VCPKG_DIR}"
fi

if [[ ! -x "${VCPKG_DIR}/vcpkg" ]]; then
  log "Bootstrapping vcpkg"
  "${VCPKG_DIR}/bootstrap-vcpkg.sh"
fi

if [[ "${UPDATE_VCPKG:-1}" == "1" ]]; then
  if ! git -C "${VCPKG_DIR}" rev-parse --git-dir >/dev/null 2>&1; then
    echo "Warning: ${VCPKG_DIR} is not a git clone; skipping vcpkg update" >&2
  else
    log "Checking for vcpkg updates (set UPDATE_VCPKG=0 to pin the current version)"
    OLD_VCPKG_REV="$(git -C "${VCPKG_DIR}" rev-parse HEAD)"
    if git -C "${VCPKG_DIR}" pull --ff-only; then
      NEW_VCPKG_REV="$(git -C "${VCPKG_DIR}" rev-parse HEAD)"
      if [[ "${OLD_VCPKG_REV}" != "${NEW_VCPKG_REV}" ]]; then
        log "vcpkg updated; re-bootstrapping and forcing package reinstall"
        "${VCPKG_DIR}/bootstrap-vcpkg.sh"
        # Force vcpkg to reinstall packages so the newer HPX port is built
        rm -rf "${BUILD_DIR}/vcpkg_installed"
      else
        log "vcpkg already up to date"
      fi
    else
      echo "Warning: vcpkg update failed (offline?); continuing with current checkout" >&2
    fi
  fi
fi

HPX_PORT_VERSION="$(grep -m1 -E '"version(-[a-z]+)?"' "${VCPKG_DIR}/ports/hpx/vcpkg.json" 2>/dev/null || true)"
log "vcpkg commit: $(git -C "${VCPKG_DIR}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
log "HPX port version: ${HPX_PORT_VERSION:-unknown}"

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

TRIALS="${TRIALS:-1}"
WARMUP="${WARMUP:-0}"

# Keep the default sizes aligned with plot_thread_size_surface.py. Override
# INPUT_SIZES with a space-separated list when a shorter diagnostic is useful.
INPUT_SIZES="${INPUT_SIZES:-1000000 2000000 4000000 8000000 12000000 16000000 24000000 32000000 48000000}"

log "Running 38-thread HPX cases with binding diagnostics"
for size in ${INPUT_SIZES}; do
  log "size=${size}, threads=38"
  "${EXE_PATH}" \
    --threads=38 \
    --size="${size}" \
    --trials="${TRIALS}" \
    --warmup="${WARMUP}" \
    --distribution=shuffle \
    --baseline=false \
    --verify=false \
    --csv=true \
    --hpx:bind=none \
    --hpx:print-bind \
    "$@"
done

log "Done. Binding diagnostics were enabled for every 38-thread run."
