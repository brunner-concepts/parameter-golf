#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR=${REPO_DIR:-$(cd -- "${SCRIPT_DIR}/.." && pwd)}
REPO_URL=${REPO_URL:-https://github.com/brunner-concepts/parameter-golf.git}
CHECKOUT_REF=${CHECKOUT_REF:-main}
VENV_DIR=${VENV_DIR:-/workspace/pgolf-venv}
FLASH_ATTN_ROOT=${FLASH_ATTN_ROOT:-/workspace/flash-attention}
# Pin a known FA3-capable upstream commit. The flash-attention repo currently
# does not publish a v3.0.0 tag, so using that symbolic ref breaks bootstrap.
FLASH_ATTN_REF=${FLASH_ATTN_REF:-6362bd3bcad059aa15fd993c6a9d5d1ee8a11418}
FLASH_ATTN_CACHE_TARBALL=${FLASH_ATTN_CACHE_TARBALL:-}
FLASH_ATTN_MODE=${FLASH_ATTN_MODE:-auto}
MAX_JOBS=${MAX_JOBS:-8}

mkdir -p "$(dirname -- "${REPO_DIR}")"

if [[ ! -d "${REPO_DIR}/.git" ]]; then
  git clone "${REPO_URL}" "${REPO_DIR}"
fi

cd "${REPO_DIR}"
CURRENT_HEAD=$(git rev-parse HEAD)
TARGET_HEAD=""

if git rev-parse --verify "${CHECKOUT_REF}" >/dev/null 2>&1; then
  TARGET_HEAD=$(git rev-parse "${CHECKOUT_REF}")
elif [[ "${CHECKOUT_REF}" == "main" || "${CHECKOUT_REF}" == "master" ]]; then
  git fetch origin "${CHECKOUT_REF}"
  TARGET_HEAD=$(git rev-parse "origin/${CHECKOUT_REF}")
fi

if [[ -n "${TARGET_HEAD}" && "${CURRENT_HEAD}" == "${TARGET_HEAD}" ]]; then
  echo "repo already at ${TARGET_HEAD}; skipping git checkout"
else
  git fetch --all --tags
  git checkout "${CHECKOUT_REF}"
  TARGET_HEAD=$(git rev-parse HEAD)
fi

echo "${TARGET_HEAD}"

python3 -m venv --system-site-packages "${VENV_DIR}"
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip wheel packaging ninja zstandard

SITE_PACKAGES=$(python - <<'PY'
import sysconfig
print(sysconfig.get_paths()["purelib"])
PY
)

if python - <<'PY'
import flash_attn_interface  # noqa: F401
import zstandard  # noqa: F401
print("flash_attn_interface already available")
PY
then
  exit 0
fi

if [[ -n "${FLASH_ATTN_CACHE_TARBALL}" && -f "${FLASH_ATTN_CACHE_TARBALL}" ]]; then
  echo "restoring flash_attn artifacts from ${FLASH_ATTN_CACHE_TARBALL}"
  mkdir -p "${SITE_PACKAGES}"
  tar -xf "${FLASH_ATTN_CACHE_TARBALL}" -C "${SITE_PACKAGES}"
  if python - <<'PY'
import flash_attn_interface  # noqa: F401
import zstandard  # noqa: F401
print("flash_attn_interface restored from cache")
PY
  then
    exit 0
  fi
  echo "cached flash_attn restore failed; falling back to source build" >&2
fi

if [[ "${FLASH_ATTN_MODE}" == "skip" ]]; then
  echo "flash_attn_interface missing and FLASH_ATTN_MODE=skip" >&2
  exit 1
fi

if [[ ! -d "${FLASH_ATTN_ROOT}/.git" ]]; then
  git clone https://github.com/Dao-AILab/flash-attention.git "${FLASH_ATTN_ROOT}"
fi

cd "${FLASH_ATTN_ROOT}"
git fetch --all --tags
git checkout "${FLASH_ATTN_REF}"

cd "${FLASH_ATTN_ROOT}/hopper"
MAX_JOBS="${MAX_JOBS}" python setup.py install

python - <<'PY'
import flash_attn_interface  # noqa: F401
import zstandard  # noqa: F401
print("flash_attn_interface and zstandard import cleanly")
PY
