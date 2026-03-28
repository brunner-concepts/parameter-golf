#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR=${REPO_DIR:-$(cd -- "${SCRIPT_DIR}/.." && pwd)}
VENV_DIR=${VENV_DIR:-/workspace/pgolf-venv}
UPSTREAM_RECORD_DIR=${UPSTREAM_RECORD_DIR:?set UPSTREAM_RECORD_DIR}
RUN_ENTRYPOINT=${RUN_ENTRYPOINT:-train_gpt.py}
NPROC_PER_NODE=${NPROC_PER_NODE:-1}
RUN_ID=${RUN_ID:-upstream_record}
LOG_PATH=${LOG_PATH:-"${REPO_DIR}/logs/${RUN_ID}.log"}
DATA_VARIANT=${DATA_VARIANT:-sp1024}

case "${DATA_VARIANT}" in
  sp1024)
    DEFAULT_DATA_PATH="${REPO_DIR}/data/datasets/fineweb10B_sp1024"
    DEFAULT_TOKENIZER_PATH="${REPO_DIR}/data/tokenizers/fineweb_1024_bpe.model"
    ;;
  *)
    echo "Unsupported DATA_VARIANT=${DATA_VARIANT}" >&2
    exit 1
    ;;
esac

export DATA_PATH=${DATA_PATH:-"${DEFAULT_DATA_PATH}"}
export TOKENIZER_PATH=${TOKENIZER_PATH:-"${DEFAULT_TOKENIZER_PATH}"}

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

mkdir -p "$(dirname -- "${LOG_PATH}")"
cd "${REPO_DIR}/${UPSTREAM_RECORD_DIR}"

python -m torch.distributed.run --standalone --nproc_per_node="${NPROC_PER_NODE}" "${RUN_ENTRYPOINT}" | tee "${LOG_PATH}"
