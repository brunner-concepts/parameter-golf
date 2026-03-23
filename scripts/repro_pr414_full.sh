#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR=${REPO_DIR:-$(cd -- "${SCRIPT_DIR}/.." && pwd)}
VENV_DIR=${VENV_DIR:-/workspace/pgolf-venv}
DATA_VARIANT=${DATA_VARIANT:-sp1024}
RUN_ID=${RUN_ID:-pr414_seed1337}
SEED=${SEED:-1337}
NPROC_PER_NODE=${NPROC_PER_NODE:-8}
LOG_PATH=${LOG_PATH:-"${REPO_DIR}/logs/${RUN_ID}.log"}

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

cd "${REPO_DIR}"
mkdir -p "$(dirname -- "${LOG_PATH}")"
python data/cached_challenge_fineweb.py --variant "${DATA_VARIANT}"

export RUN_ID
export SEED

python -m torch.distributed.run --standalone --nproc_per_node="${NPROC_PER_NODE}" \
  third_party/upstream_prs/pr414/train_gpt.py | tee "${LOG_PATH}"
