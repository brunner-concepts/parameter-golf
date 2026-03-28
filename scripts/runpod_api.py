#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REST_BASE = "https://rest.runpod.io/v1"


class RunPodApiError(RuntimeError):
    pass


def run_json(cmd: list[str]) -> Any:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


def load_api_key() -> str:
    for env_name in ("RUNPOD_API_KEY",):
        value = os.environ.get(env_name)
        if value:
            return value

    runpod_home = Path(os.environ.get("RUNPOD_HOME", "~/.runpod")).expanduser()
    config_path = runpod_home / "config.toml"
    if not config_path.exists():
        raise RunPodApiError(f"RunPod config not found at {config_path}")

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))

    def walk(node: Any) -> str | None:
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = str(key).lower()
                if lowered in {"apikey", "api_key", "token"} and isinstance(value, str) and value.strip():
                    return value.strip()
                nested = walk(value)
                if nested:
                    return nested
        elif isinstance(node, list):
            for item in node:
                nested = walk(item)
                if nested:
                    return nested
        return None

    api_key = walk(data)
    if not api_key:
        raise RunPodApiError(f"Unable to find RunPod API key in {config_path}")
    return api_key


def rest_request(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    api_key = load_api_key()
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{REST_BASE}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RunPodApiError(f"{method} {path} failed: {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise RunPodApiError(f"{method} {path} failed: {exc}") from exc
    return json.loads(raw) if raw.strip() else {}


def list_network_volumes() -> list[dict[str, Any]]:
    response = rest_request("GET", "/networkvolumes")
    return response if isinstance(response, list) else []


def get_network_volume(volume_id: str) -> dict[str, Any]:
    return rest_request("GET", f"/networkvolumes/{volume_id}")


def create_network_volume(name: str, data_center_id: str, size_gb: int) -> dict[str, Any]:
    return rest_request(
        "POST",
        "/networkvolumes",
        {
            "name": name,
            "dataCenterId": data_center_id,
            "size": int(size_gb),
        },
    )


def create_pod(payload: dict[str, Any]) -> dict[str, Any]:
    return rest_request("POST", "/pods", payload)


def delete_pod(pod_id: str) -> None:
    subprocess.run(["runpodctl", "pod", "delete", pod_id], capture_output=True, text=True, check=False)


def wait_for_ssh(pod_id: str, timeout_s: int) -> dict[str, Any]:
    started = time.time()
    last_status = "unknown"
    while time.time() - started < timeout_s:
        pod = run_json(["runpodctl", "pod", "get", pod_id])
        last_status = str(pod.get("desiredStatus"))
        ssh = pod.get("ssh") or {}
        if pod.get("desiredStatus") == "RUNNING" and "ip" in ssh and "port" in ssh:
            return pod
        if last_status == "EXITED":
            raise RunPodApiError(f"Pod {pod_id} exited before SSH became available.")
        time.sleep(5)
    raise RunPodApiError(f"Timed out waiting for SSH on pod {pod_id}; last status was {last_status}.")


def remote_ssh_cmd(pod: dict[str, Any]) -> list[str]:
    ssh = pod["ssh"]
    return [
        "ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-i",
        str(ssh["ssh_key"]["path"]),
        f"root@{ssh['ip']}",
        "-p",
        str(ssh["port"]),
    ]


def remote_scp_cmd(pod: dict[str, Any]) -> list[str]:
    ssh = pod["ssh"]
    return [
        "scp",
        "-O",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-i",
        str(ssh["ssh_key"]["path"]),
        "-P",
        str(ssh["port"]),
    ]


def datacenters_for_gpu(gpu_id: str, preferred_ids: list[str] | None = None) -> list[str]:
    preferred_ids = preferred_ids or []
    rows = run_json(["runpodctl", "datacenter", "list"])
    matching: list[str] = []
    fallback: list[str] = []
    for row in rows:
        dc_id = str(row.get("id"))
        availability = row.get("gpuAvailability") or []
        has_gpu = False
        for item in availability:
            if str(item.get("gpuId")) == gpu_id and str(item.get("stockStatus")).lower() in {"high", "medium"}:
                has_gpu = True
                break
        if not has_gpu:
            continue
        if dc_id in preferred_ids:
            matching.append(dc_id)
        else:
            fallback.append(dc_id)
    ordered = [dc_id for dc_id in preferred_ids if dc_id in matching] + [dc_id for dc_id in fallback if dc_id not in matching]
    return ordered

