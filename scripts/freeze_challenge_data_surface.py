#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def dataset_dir_for_variant(name: str) -> str:
    if name == "byte260":
        return "fineweb10B_byte260"
    if name.startswith("sp") and name[2:].isdigit():
        return f"fineweb10B_{name}"
    raise ValueError(f"unsupported variant {name!r}; expected byte260 or sp<VOCAB_SIZE>")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freeze a challenge-data manifest and shard surface for a reproducible rerun.")
    parser.add_argument("--variant", default="sp1024")
    parser.add_argument("--repo-id", default="willdepueoai/parameter-golf")
    parser.add_argument("--remote-root-prefix", default="datasets")
    parser.add_argument(
        "--manifest-out",
        default="11_RUN_CONTROL/control_plane/data_surfaces/pr868_manifest_snapshot.json",
    )
    parser.add_argument(
        "--surface-out",
        default="11_RUN_CONTROL/control_plane/data_surfaces/pr868_surface_snapshot.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest_out = Path(args.manifest_out).resolve()
    surface_out = Path(args.surface_out).resolve()
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    surface_out.parent.mkdir(parents=True, exist_ok=True)

    api = HfApi()
    dataset_info = api.dataset_info(args.repo_id)
    revision = dataset_info.sha
    if not revision:
        raise RuntimeError(f"Could not resolve dataset revision for {args.repo_id}")

    remote_manifest_path = f"{args.remote_root_prefix}/manifest.json"
    cached_manifest = Path(
        hf_hub_download(
            repo_id=args.repo_id,
            filename="manifest.json",
            subfolder=args.remote_root_prefix,
            repo_type="dataset",
            revision=revision,
        )
    )
    manifest = json.loads(cached_manifest.read_text(encoding="utf-8"))
    dataset_name = dataset_dir_for_variant(args.variant)
    dataset_entry = next((item for item in manifest.get("datasets", []) if item.get("name") == dataset_name), None)
    if dataset_entry is None:
        raise RuntimeError(f"Dataset {dataset_name} not found in {remote_manifest_path}")
    tokenizer_name = dataset_entry.get("tokenizer_name")
    tokenizer_entry = next((item for item in manifest.get("tokenizers", []) if item.get("name") == tokenizer_name), None)
    if tokenizer_entry is None:
        raise RuntimeError(f"Tokenizer {tokenizer_name} not found in {remote_manifest_path}")

    manifest_out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    files_train = int((dataset_entry.get("stats") or {}).get("files_train", 0))
    files_val = int((dataset_entry.get("stats") or {}).get("files_val", 0))
    surface = {
        "frozen_at": utc_now(),
        "repo_id": args.repo_id,
        "repo_revision": revision,
        "remote_root_prefix": args.remote_root_prefix,
        "remote_manifest_path": remote_manifest_path,
        "variant": args.variant,
        "dataset_name": dataset_name,
        "tokenizer_name": tokenizer_name,
        "tokenizer_entry": tokenizer_entry,
        "manifest_path": str(manifest_out),
        "manifest_sha256": hashlib.sha256(manifest_out.read_bytes()).hexdigest(),
        "manifest_cache_path": str(cached_manifest),
        "dataset_stats": dataset_entry.get("stats", {}),
        "expected_train_shards": [f"fineweb_train_{index:06d}.bin" for index in range(files_train)],
        "expected_val_shards": [f"fineweb_val_{index:06d}.bin" for index in range(files_val)],
    }
    surface_out.write_text(json.dumps(surface, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
