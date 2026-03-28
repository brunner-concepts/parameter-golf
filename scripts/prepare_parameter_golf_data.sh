#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR=${REPO_DIR:-$(cd -- "${SCRIPT_DIR}/.." && pwd)}
VENV_DIR=${VENV_DIR:-/workspace/pgolf-venv}
DATA_VARIANT=${DATA_VARIANT:-sp1024}
TRAIN_SHARDS=${TRAIN_SHARDS:-}

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

cd "${REPO_DIR}"

ARGS=(data/cached_challenge_fineweb.py --variant "${DATA_VARIANT}")
if [[ -n "${TRAIN_SHARDS}" ]]; then
  ARGS+=(--train-shards "${TRAIN_SHARDS}")
fi

python "${ARGS[@]}"
