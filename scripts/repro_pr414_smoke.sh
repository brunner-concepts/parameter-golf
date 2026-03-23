#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR=${REPO_DIR:-$(cd -- "${SCRIPT_DIR}/.." && pwd)}
VENV_DIR=${VENV_DIR:-/workspace/pgolf-venv}
DATA_VARIANT=${DATA_VARIANT:-sp1024}
TRAIN_SHARDS=${TRAIN_SHARDS:-1}
RUN_ID=${RUN_ID:-pr414_smoke}
SEED=${SEED:-1337}
TRAIN_BATCH_TOKENS=${TRAIN_BATCH_TOKENS:-131072}
VAL_BATCH_SIZE=${VAL_BATCH_SIZE:-65536}
TRAIN_SEQ_LEN=${TRAIN_SEQ_LEN:-1024}
EVAL_SEQ_LEN=${EVAL_SEQ_LEN:-1024}
MAX_WALLCLOCK_SECONDS=${MAX_WALLCLOCK_SECONDS:-120}
VAL_LOSS_EVERY=${VAL_LOSS_EVERY:-0}
TRAIN_LOG_EVERY=${TRAIN_LOG_EVERY:-20}
NPROC_PER_NODE=${NPROC_PER_NODE:-1}
LOG_PATH=${LOG_PATH:-"${REPO_DIR}/logs/${RUN_ID}.log"}

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

cd "${REPO_DIR}"
mkdir -p "$(dirname -- "${LOG_PATH}")"
python data/cached_challenge_fineweb.py --variant "${DATA_VARIANT}" --train-shards "${TRAIN_SHARDS}"

export RUN_ID
export SEED
export TRAIN_BATCH_TOKENS
export VAL_BATCH_SIZE
export TRAIN_SEQ_LEN
export EVAL_SEQ_LEN
export MAX_WALLCLOCK_SECONDS
export VAL_LOSS_EVERY
export TRAIN_LOG_EVERY

python -m torch.distributed.run --standalone --nproc_per_node="${NPROC_PER_NODE}" \
  third_party/upstream_prs/pr414/train_gpt.py | tee "${LOG_PATH}"
