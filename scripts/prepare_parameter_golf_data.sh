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

if [[ -n "${RUN_DIR:-}" ]]; then
  SNAPSHOT_DIR="${RUN_DIR}/artifacts/challenge_data"
  mkdir -p "${SNAPSHOT_DIR}"
  export SNAPSHOT_DIR
  python <<'PY'
import hashlib
import json
import os
from pathlib import Path

repo_dir = Path(os.environ["REPO_DIR"])
snapshot_dir = Path(os.environ["SNAPSHOT_DIR"])
variant = os.environ.get("DATA_VARIANT", "sp1024")
train_shards_requested = os.environ.get("TRAIN_SHARDS") or None
manifest_path = repo_dir / "data" / "manifest.json"
datasets_root = repo_dir / "data" / "datasets"

if variant == "byte260":
    dataset_name = "fineweb10B_byte260"
elif variant.startswith("sp") and variant[2:].isdigit():
    dataset_name = f"fineweb10B_{variant}"
else:
    raise ValueError(f"unsupported DATA_VARIANT={variant!r}")

dataset_dir = datasets_root / dataset_name
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
dataset_entry = next((item for item in manifest.get("datasets", []) if item.get("name") == dataset_name), None)
if dataset_entry is None:
    raise ValueError(f"{dataset_name} not present in manifest {manifest_path}")

snapshot = {
    "repo_id": os.environ.get("MATCHED_FINEWEB_REPO_ID", "willdepueoai/parameter-golf"),
    "remote_root_prefix": os.environ.get("MATCHED_FINEWEB_REMOTE_ROOT_PREFIX", "datasets"),
    "variant": variant,
    "dataset_name": dataset_name,
    "dataset_dir": str(dataset_dir),
    "manifest_path": str(manifest_path),
    "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    "train_shards_requested": int(train_shards_requested) if train_shards_requested else None,
    "manifest_dataset_stats": dataset_entry.get("stats", {}),
    "downloaded_train_files": sorted(path.name for path in dataset_dir.glob("fineweb_train_*.bin")),
    "downloaded_val_files": sorted(path.name for path in dataset_dir.glob("fineweb_val_*.bin")),
}

(snapshot_dir / "challenge_data_snapshot.json").write_text(
    json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
(snapshot_dir / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
fi
