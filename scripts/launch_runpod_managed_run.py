#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


DEFAULT_TEMPLATE_ID = "y5cejece4j"
COMPUTE_DEFAULTS = {
    "8xH100-SXM": {
        "gpu_id": "NVIDIA H100 80GB HBM3",
        "gpu_count": 8,
        "min_balance": 25.0,
    },
    "1xH100-smoke": {
        "gpu_id": "NVIDIA H100 80GB HBM3",
        "gpu_count": 1,
        "min_balance": 5.0,
    },
}


def run_json(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


def run_text(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return proc.stdout


def load_spec(spec_path: Path) -> dict[str, Any]:
    return json.loads(spec_path.read_text(encoding="utf-8"))


def infer_defaults(spec: dict[str, Any]) -> dict[str, Any]:
    return COMPUTE_DEFAULTS.get(spec.get("compute_tier"), COMPUTE_DEFAULTS["1xH100-smoke"])


def wait_for_ssh(pod_id: str, timeout_s: int) -> dict[str, Any]:
    started = time.time()
    while time.time() - started < timeout_s:
        pod = run_json(["runpodctl", "pod", "get", pod_id])
        ssh = pod.get("ssh") or {}
        if pod.get("desiredStatus") == "RUNNING" and "ip" in ssh and "port" in ssh:
            return pod
        time.sleep(5)
    raise RuntimeError(f"Timed out waiting for SSH on pod {pod_id}")


def build_remote_launch_command(repo_ref: str, spec_path: str, remote_state_dir: str, session_name: str) -> str:
    return "\n".join(
        [
            "set -euo pipefail",
            "cd /workspace",
            "if [[ ! -d parameter-golf/.git ]]; then git clone https://github.com/brunner-concepts/parameter-golf.git; fi",
            "cd /workspace/parameter-golf",
            "git fetch origin",
            f"git checkout {repo_ref}",
            f"git pull --ff-only origin {repo_ref} || true",
            f"mkdir -p {remote_state_dir}",
            f"tmux kill-session -t {session_name} 2>/dev/null || true",
            (
                f"tmux new-session -d -s {session_name} "
                f"\"cd /workspace/parameter-golf && "
                f"python3 scripts/run_watchdog.py run --state-dir {remote_state_dir} {spec_path} "
                f"| tee /workspace/{session_name}.log\""
            ),
            "tmux ls",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch a managed RunPod session and detach a local mirror process.")
    parser.add_argument("spec", help="Path to the run spec to execute remotely.")
    parser.add_argument("--template-id", default=DEFAULT_TEMPLATE_ID)
    parser.add_argument("--gpu-id")
    parser.add_argument("--gpu-count", type=int)
    parser.add_argument("--container-disk-gb", type=int, default=50)
    parser.add_argument("--volume-gb", type=int, default=50)
    parser.add_argument("--pod-name")
    parser.add_argument("--repo-ref", default="main")
    parser.add_argument("--remote-state-dir", default="/workspace/run_control")
    parser.add_argument("--mirror-interval", type=float, default=15.0)
    parser.add_argument("--wait-timeout", type=int, default=600)
    parser.add_argument("--notify-macos", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    spec_path = Path(args.spec).resolve()
    spec = load_spec(spec_path)
    defaults = infer_defaults(spec)

    user = run_json(["runpodctl", "user"])
    min_balance = defaults["min_balance"]
    if float(user["clientBalance"]) < min_balance:
        raise RuntimeError(
            f"Insufficient RunPod balance (${user['clientBalance']:.2f}). "
            f"Top up to at least ${min_balance:.2f} before launching {spec['run_id']}."
        )

    gpu_id = args.gpu_id or defaults["gpu_id"]
    gpu_count = args.gpu_count or defaults["gpu_count"]
    pod_name = args.pod_name or f"{spec['run_id']}-{gpu_count}x"

    create = run_json(
        [
            "runpodctl",
            "pod",
            "create",
            "--name",
            pod_name,
            "--template-id",
            args.template_id,
            "--gpu-id",
            gpu_id,
            "--gpu-count",
            str(gpu_count),
            "--container-disk-in-gb",
            str(args.container_disk_gb),
            "--volume-in-gb",
            str(args.volume_gb),
            "--ssh",
        ]
    )
    pod = create[0] if isinstance(create, list) else create
    pod_id = pod["id"]
    pod = wait_for_ssh(pod_id, args.wait_timeout)
    ssh = pod["ssh"]

    ssh_cmd = [
        "ssh",
        "-i",
        str(ssh["ssh_key"]["path"]),
        f"root@{ssh['ip']}",
        "-p",
        str(ssh["port"]),
    ]
    session_name = spec["run_id"]
    try:
        spec_rel = spec_path.relative_to(repo_root)
    except ValueError as exc:
        raise RuntimeError(f"Spec path {spec_path} must live under repo root {repo_root}") from exc
    remote_spec_path = Path("/workspace/parameter-golf") / spec_rel
    remote_command = build_remote_launch_command(args.repo_ref, str(remote_spec_path), args.remote_state_dir, session_name)
    run_text(ssh_cmd + [remote_command])

    local_dir = repo_root / "11_RUN_CONTROL" / "live" / spec["run_id"]
    local_dir.mkdir(parents=True, exist_ok=True)
    mirror_log = local_dir / "mirror.log"
    mirror_cmd = [
        sys.executable,
        str(repo_root / "scripts" / "mirror_runpod_watchdog.py"),
        "--pod-id",
        pod_id,
        "--remote-state-dir",
        args.remote_state_dir,
        "--local-dir",
        str(local_dir),
        "--interval",
        str(args.mirror_interval),
    ]
    if args.notify_macos:
        mirror_cmd.append("--notify-macos")
    with mirror_log.open("a", encoding="utf-8") as handle:
        proc = subprocess.Popen(
            mirror_cmd,
            stdout=handle,
            stderr=subprocess.STDOUT,
            cwd=str(repo_root),
            start_new_session=True,
            text=True,
        )

    launch_summary = {
        "pod_id": pod_id,
        "pod_name": pod_name,
        "run_id": spec["run_id"],
        "mirror_pid": proc.pid,
        "mirror_log": str(mirror_log.resolve()),
        "local_dir": str(local_dir.resolve()),
        "ssh_command": ssh["ssh_command"],
    }
    (local_dir / "launch.json").write_text(json.dumps(launch_summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(launch_summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
