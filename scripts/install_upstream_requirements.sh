#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR=${REPO_DIR:-$(cd -- "${SCRIPT_DIR}/.." && pwd)}
VENV_DIR=${VENV_DIR:-/workspace/pgolf-venv}
UPSTREAM_RECORD_DIR=${UPSTREAM_RECORD_DIR:-}
UPSTREAM_REQUIREMENTS=${UPSTREAM_REQUIREMENTS:-}

if [[ -z "${UPSTREAM_REQUIREMENTS}" && -n "${UPSTREAM_RECORD_DIR}" ]]; then
  UPSTREAM_REQUIREMENTS="${REPO_DIR}/${UPSTREAM_RECORD_DIR}/requirements.txt"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

if [[ -z "${UPSTREAM_REQUIREMENTS}" ]]; then
  echo "UPSTREAM_REQUIREMENTS not set; nothing to install"
  exit 0
fi

if [[ ! -f "${UPSTREAM_REQUIREMENTS}" ]]; then
  echo "requirements file not found at ${UPSTREAM_REQUIREMENTS}; skipping"
  exit 0
fi

python -m pip install -r "${UPSTREAM_REQUIREMENTS}"
