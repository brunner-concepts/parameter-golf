#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import runpod_api


DEFAULT_TEMPLATE_ID = "y5cejece4j"
DEFAULT_GPU_ID = "NVIDIA H100 80GB HBM3"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def notify(title: str, body: str) -> None:
    webhook = os.environ.get("RUN_NOTIFY_WEBHOOK_URL")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if webhook:
        payload = json.dumps({"title": title, "body": body}).encode("utf-8")
        request = urllib.request.Request(
            webhook,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15):
                pass
        except Exception:
            pass
    if bot_token and chat_id:
        payload = urllib.parse.urlencode({"chat_id": chat_id, "text": f"{title}\n{body}"}).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15):
                pass
        except Exception:
            pass


def provider_state_defaults(config: dict[str, Any], cache_path: Path) -> dict[str, Any]:
    mount_path = str(config.get("mount_path", "/workspace/shared"))
    relative_asset_path = str(config.get("flash_attn_asset_relative_path", f"cache/{cache_path.name}"))
    return {
        "updated_at": utc_now(),
        "status": "initializing",
        "volume_name": str(config.get("volume_name_prefix", "parameter-golf-shared-cache")),
        "volume_size_gb": int(config.get("size_gb", 50)),
        "mount_path": mount_path,
        "flash_attn_local_path": str(cache_path),
        "flash_attn_relative_path": relative_asset_path,
        "flash_attn_remote_path": f"{mount_path.rstrip('/')}/{relative_asset_path.lstrip('/')}",
        "seed_gpu_id": str(config.get("seed_gpu_id", DEFAULT_GPU_ID)),
        "template_id": str(config.get("template_id", DEFAULT_TEMPLATE_ID)),
        "preferred_data_center_ids": list(config.get("preferred_data_center_ids", [])),
    }


def choose_datacenter(config: dict[str, Any]) -> str:
    preferred = list(config.get("preferred_data_center_ids", []))
    gpu_id = str(config.get("target_gpu_id", DEFAULT_GPU_ID))
    datacenters = runpod_api.datacenters_for_gpu(gpu_id, preferred)
    if not datacenters:
        raise RuntimeError(f"No datacenter with available {gpu_id} found for provider storage.")
    return datacenters[0]


def existing_volume(state: dict[str, Any]) -> dict[str, Any] | None:
    volume_id = state.get("volume_id")
    if not volume_id:
        return None
    try:
        return runpod_api.get_network_volume(str(volume_id))
    except Exception:
        return None


def find_named_volume(name: str) -> dict[str, Any] | None:
    for volume in runpod_api.list_network_volumes():
        if str(volume.get("name")) == name:
            return volume
    return None


def create_seed_pod(
    volume_id: str,
    data_center_id: str,
    mount_path: str,
    template_id: str,
    gpu_id: str,
    container_disk_gb: int,
    volume_gb: int,
) -> dict[str, Any]:
    payload = {
        "name": f"pgolf-seed-{int(time.time())}",
        "cloudType": "SECURE",
        "computeType": "GPU",
        "templateId": template_id,
        "gpuTypeIds": [gpu_id],
        "gpuTypePriority": "availability",
        "gpuCount": 1,
        "dataCenterIds": [data_center_id],
        "dataCenterPriority": "availability",
        "containerDiskInGb": int(container_disk_gb),
        "volumeInGb": int(volume_gb),
        "volumeMountPath": mount_path,
        "networkVolumeId": volume_id,
        "ports": ["22/tcp"],
        "supportPublicIp": True,
        "interruptible": False,
    }
    return runpod_api.create_pod(payload)


def upload_asset_to_seed_pod(
    pod: dict[str, Any],
    local_path: Path,
    remote_path: str,
    timeout_s: int,
) -> int:
    ssh_cmd = runpod_api.remote_ssh_cmd(pod)
    scp_cmd = runpod_api.remote_scp_cmd(pod)
    remote_dir = shlex.quote(str(Path(remote_path).parent))
    subprocess.run(ssh_cmd + [f"mkdir -p {remote_dir}"], capture_output=True, text=True, check=True, timeout=60)
    subprocess.run(
        scp_cmd + [str(local_path), f"root@{pod['ssh']['ip']}:{remote_path}"],
        capture_output=True,
        text=True,
        check=True,
        timeout=timeout_s,
    )
    stat_proc = subprocess.run(
        ssh_cmd + [f"python3 - <<'PY'\nfrom pathlib import Path\nprint(Path({remote_path!r}).stat().st_size)\nPY"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return int(stat_proc.stdout.strip())


def ensure_storage_ready(
    config: dict[str, Any],
    state_path: Path,
    decisions_path: Path,
) -> dict[str, Any]:
    cache_path = Path(config.get("flash_attn_local_path") or "").expanduser()
    if not cache_path.exists():
        raise RuntimeError(f"Local FlashAttention cache not found: {cache_path}")

    state = read_json_if_exists(state_path)
    defaults = provider_state_defaults(config, cache_path)
    for key, value in defaults.items():
        state.setdefault(key, value)

    volume = existing_volume(state)
    if volume is None:
        named = find_named_volume(str(state["volume_name"]))
        if named is not None:
            volume = named
        else:
            data_center_id = choose_datacenter(config)
            volume = runpod_api.create_network_volume(str(state["volume_name"]), data_center_id, int(state["volume_size_gb"]))
            append_jsonl(
                decisions_path,
                {
                    "event": "provider_volume_created",
                    "timestamp": utc_now(),
                    "volume_id": volume.get("id"),
                    "data_center_id": volume.get("dataCenterId"),
                    "name": volume.get("name"),
                    "size_gb": volume.get("size"),
                },
            )
            notify(
                "Parameter Golf provider volume created",
                "\n".join(
                    [
                        f"volume={volume.get('id')}",
                        f"dc={volume.get('dataCenterId')}",
                        f"name={volume.get('name')}",
                    ]
                ),
            )

    state.update(
        {
            "volume_id": volume.get("id"),
            "data_center_id": volume.get("dataCenterId"),
            "status": "volume_ready",
            "updated_at": utc_now(),
        }
    )
    atomic_write_json(state_path, state)

    seeded = state.get("seeded_flash_attn") or {}
    expected_remote = state["flash_attn_remote_path"]
    if seeded.get("status") == "ready" and seeded.get("remote_path") == expected_remote:
        state["status"] = "ready"
        state["updated_at"] = utc_now()
        atomic_write_json(state_path, state)
        return state

    seed_pod = create_seed_pod(
        volume_id=str(state["volume_id"]),
        data_center_id=str(state["data_center_id"]),
        mount_path=str(state["mount_path"]),
        template_id=str(state["template_id"]),
        gpu_id=str(state["seed_gpu_id"]),
        container_disk_gb=int(config.get("seed_container_disk_gb", 30)),
        volume_gb=int(config.get("seed_volume_gb", 10)),
    )
    seed_pod_id = str(seed_pod["id"])
    state.update(
        {
            "status": "seeding",
            "seed_pod_id": seed_pod_id,
            "seed_started_at": utc_now(),
            "updated_at": utc_now(),
        }
    )
    atomic_write_json(state_path, state)
    append_jsonl(
        decisions_path,
        {
            "event": "provider_seed_started",
            "timestamp": utc_now(),
            "volume_id": state["volume_id"],
            "seed_pod_id": seed_pod_id,
        },
    )
    notify(
        "Parameter Golf provider seed started",
        "\n".join([f"volume={state['volume_id']}", f"seed_pod={seed_pod_id}", f"asset={expected_remote}"]),
    )

    try:
        pod = runpod_api.wait_for_ssh(seed_pod_id, int(config.get("seed_wait_timeout_seconds", 600)))
        size_bytes = upload_asset_to_seed_pod(
            pod,
            cache_path,
            expected_remote,
            int(config.get("seed_copy_timeout_seconds", 1800)),
        )
    except Exception as exc:
        runpod_api.delete_pod(seed_pod_id)
        state.update(
            {
                "status": "failed",
                "updated_at": utc_now(),
                "last_error": str(exc),
                "seed_failures": int(state.get("seed_failures", 0)) + 1,
            }
        )
        atomic_write_json(state_path, state)
        append_jsonl(
            decisions_path,
            {
                "event": "provider_seed_failed",
                "timestamp": utc_now(),
                "seed_pod_id": seed_pod_id,
                "error": str(exc),
            },
        )
        notify(
            "Parameter Golf provider seed failed",
            "\n".join([f"seed_pod={seed_pod_id}", f"error={str(exc)}"])[:3500],
        )
        raise

    runpod_api.delete_pod(seed_pod_id)
    seeded_payload = {
        "status": "ready",
        "remote_path": expected_remote,
        "local_path": str(cache_path),
        "seeded_at": utc_now(),
        "size_bytes": size_bytes,
    }
    state.update(
        {
            "status": "ready",
            "seeded_flash_attn": seeded_payload,
            "seed_completed_at": utc_now(),
            "updated_at": utc_now(),
        }
    )
    atomic_write_json(state_path, state)
    append_jsonl(
        decisions_path,
        {
            "event": "provider_seed_ready",
            "timestamp": utc_now(),
            "volume_id": state["volume_id"],
            "remote_path": expected_remote,
            "size_bytes": size_bytes,
        },
    )
    notify(
        "Parameter Golf provider seed ready",
        "\n".join([f"volume={state['volume_id']}", f"path={expected_remote}", f"bytes={size_bytes}"]),
    )
    return state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage provider-side staged assets for Parameter Golf.")
    parser.add_argument("command", choices=["ensure", "status"])
    parser.add_argument("--state-file", default="11_RUN_CONTROL/control_plane/state/provider_storage_state.json")
    parser.add_argument("--decisions-file", default="11_RUN_CONTROL/control_plane/state/decisions.jsonl")
    parser.add_argument("--cache-path", default="11_RUN_CONTROL/cache/flash_attn_3_py312_6362bd3.tar.zst")
    parser.add_argument("--volume-name-prefix", default="parameter-golf-shared-cache")
    parser.add_argument("--size-gb", type=int, default=50)
    parser.add_argument("--mount-path", default="/workspace/shared")
    parser.add_argument("--relative-asset-path", default="")
    parser.add_argument("--target-gpu-id", default=DEFAULT_GPU_ID)
    parser.add_argument("--seed-gpu-id", default=DEFAULT_GPU_ID)
    parser.add_argument("--template-id", default=DEFAULT_TEMPLATE_ID)
    parser.add_argument("--preferred-datacenters", default="")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = repo_root()
    state_path = (root / args.state_file).resolve()
    decisions_path = (root / args.decisions_file).resolve()
    cache_path = (root / args.cache_path).resolve()
    config = {
        "flash_attn_local_path": str(cache_path),
        "volume_name_prefix": args.volume_name_prefix,
        "size_gb": args.size_gb,
        "mount_path": args.mount_path,
        "flash_attn_asset_relative_path": args.relative_asset_path or f"cache/{cache_path.name}",
        "target_gpu_id": args.target_gpu_id,
        "seed_gpu_id": args.seed_gpu_id,
        "template_id": args.template_id,
        "preferred_data_center_ids": [item.strip() for item in args.preferred_datacenters.split(",") if item.strip()],
    }
    if args.command == "status":
        payload = read_json_if_exists(state_path)
    else:
        payload = ensure_storage_ready(config, state_path, decisions_path)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
