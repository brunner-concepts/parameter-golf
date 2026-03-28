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
DEFAULT_FLASH_ATTN_CACHE = "11_RUN_CONTROL/cache/flash_attn_3_py312_6362bd3.tar"
COMPUTE_DEFAULTS = {
    "8xH100-SXM": {
        "gpu_id": "NVIDIA H100 80GB HBM3",
        "gpu_count": 8,
        "min_balance": 25.0,
    },
    "1xH100-smoke": {
        "gpu_id": "NVIDIA H100 PCIe",
        "gpu_count": 1,
        "min_balance": 5.0,
    },
}


class LaunchError(RuntimeError):
    def __init__(self, message: str, launch_summary: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.launch_summary = launch_summary or {}


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


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


def build_parser() -> argparse.ArgumentParser:
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
    parser.add_argument("--mirror-interval", type=float, default=10.0)
    parser.add_argument("--mirror-log-lines", type=int, default=120)
    parser.add_argument("--wait-timeout", type=int, default=600)
    parser.add_argument("--remote-launch-retries", type=int, default=3)
    parser.add_argument("--remote-launch-retry-delay", type=float, default=5.0)
    parser.add_argument("--flash-attn-cache-tarball")
    parser.add_argument("--min-balance", type=float)
    parser.add_argument("--notify-macos", action="store_true")
    parser.add_argument("--webhook-url")
    parser.add_argument("--telegram-bot-token")
    parser.add_argument("--telegram-chat-id")
    parser.add_argument("--mirror-exit-when-inactive", action=argparse.BooleanOptionalAction, default=True)
    return parser


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
            raise LaunchError(f"Pod {pod_id} exited before SSH became available.")
        time.sleep(5)
    raise LaunchError(f"Timed out waiting for SSH on pod {pod_id}; last status was {last_status}.")


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


def stop_pod_quietly(pod_id: str) -> None:
    subprocess.run(["runpodctl", "pod", "stop", pod_id], capture_output=True, text=True, check=False)


def build_remote_launch_command(
    repo_ref: str,
    remote_spec_path: str,
    remote_state_dir: str,
    session_name: str,
    extra_env: dict[str, str] | None = None,
) -> str:
    env_prefix = ""
    if extra_env:
        env_prefix = " ".join(f"{key}={shlex_quote(value)}" for key, value in sorted(extra_env.items())) + " "
    tmux_body = (
        "cd /workspace/parameter-golf && "
        f"{env_prefix}python3 scripts/run_watchdog.py run --state-dir {shlex_quote(remote_state_dir)} "
        f"{shlex_quote(remote_spec_path)} | tee /workspace/{session_name}.log"
    )
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
            f"tmux new-session -d -s {session_name} {shlex_quote(tmux_body)}",
            "tmux ls",
        ]
    )


def shlex_quote(value: str) -> str:
    import shlex

    return shlex.quote(value)


def resolve_flash_attn_cache(root: Path, args: argparse.Namespace) -> Path | None:
    requested = getattr(args, "flash_attn_cache_tarball", None)
    if requested:
        cache_path = Path(requested).expanduser().resolve()
        if not cache_path.exists():
            raise LaunchError(f"FlashAttention cache tarball not found: {cache_path}")
        return cache_path
    default = (root / DEFAULT_FLASH_ATTN_CACHE).resolve()
    if default.exists():
        return default
    return None


def build_mirror_command(args: argparse.Namespace, pod_id: str, local_dir: Path) -> list[str]:
    mirror_cmd = [
        sys.executable,
        str(repo_root() / "scripts" / "mirror_runpod_watchdog.py"),
        "--pod-id",
        pod_id,
        "--remote-state-dir",
        args.remote_state_dir,
        "--local-dir",
        str(local_dir),
        "--interval",
        str(args.mirror_interval),
        "--log-lines",
        str(args.mirror_log_lines),
    ]
    if args.notify_macos:
        mirror_cmd.append("--notify-macos")
    if args.webhook_url:
        mirror_cmd.extend(["--webhook-url", args.webhook_url])
    if args.telegram_bot_token:
        mirror_cmd.extend(["--telegram-bot-token", args.telegram_bot_token])
    if args.telegram_chat_id:
        mirror_cmd.extend(["--telegram-chat-id", args.telegram_chat_id])
    if not args.mirror_exit_when_inactive:
        mirror_cmd.append("--no-exit-when-inactive")
    return mirror_cmd


def reset_live_dir(local_dir: Path) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "pod.json",
        "mirror_state.json",
        "current_state.json",
        "heartbeat.json",
        "status.txt",
        "next_action.txt",
        "terminal_result.json",
        "active_log.tail.txt",
        "summary.md",
    ):
        path = local_dir / name
        if path.exists():
            path.unlink()


def write_launch_summary(local_dir: Path, launch_summary: dict[str, Any]) -> None:
    local_dir.mkdir(parents=True, exist_ok=True)
    (local_dir / "launch.json").write_text(json.dumps(launch_summary, indent=2) + "\n", encoding="utf-8")


def launch_managed_run(args: argparse.Namespace) -> dict[str, Any]:
    root = repo_root()
    spec_path = Path(args.spec).resolve()
    spec = load_spec(spec_path)
    defaults = infer_defaults(spec)
    remote_launch_retries = int(getattr(args, "remote_launch_retries", 3))
    remote_launch_retry_delay = float(getattr(args, "remote_launch_retry_delay", 5.0))
    local_dir = root / "11_RUN_CONTROL" / "live" / spec["run_id"]
    reset_live_dir(local_dir)

    user = run_json(["runpodctl", "user"])
    min_balance = float(args.min_balance if args.min_balance is not None else defaults["min_balance"])
    if float(user["clientBalance"]) < min_balance:
        raise LaunchError(
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
    launch_summary: dict[str, Any] = {
        "pod_id": pod_id,
        "pod_name": pod_name,
        "run_id": spec["run_id"],
        "spec_path": str(spec_path),
        "balance_at_launch": float(user["clientBalance"]),
        "spend_limit": user.get("spendLimit"),
        "compute_tier": spec.get("compute_tier"),
        "gpu_id": gpu_id,
        "gpu_count": gpu_count,
        "launch_phase": "pod_created",
    }
    write_launch_summary(local_dir, launch_summary)

    try:
        pod = wait_for_ssh(pod_id, args.wait_timeout)
        ssh_cmd = remote_ssh_cmd(pod)
        scp_cmd = remote_scp_cmd(pod)
        launch_summary.update(
            {
                "launch_phase": "ssh_ready",
                "ssh_command": pod["ssh"]["ssh_command"],
            }
        )
        write_launch_summary(local_dir, launch_summary)
        remote_spec_dir = Path(args.remote_state_dir) / "specs"
        remote_spec_path = remote_spec_dir / spec_path.name
        mkdir_proc = subprocess.run(
            ssh_cmd + [f"mkdir -p {shlex_quote(str(remote_spec_dir))}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if mkdir_proc.returncode != 0:
            stop_pod_quietly(pod_id)
            details = mkdir_proc.stderr.strip() or mkdir_proc.stdout.strip() or f"ssh exited {mkdir_proc.returncode}"
            raise LaunchError(
                f"Failed to create remote spec directory on pod {pod_id}: {details}",
                launch_summary,
            )
        launch_summary.update(
            {
                "launch_phase": "copying_spec",
                "remote_spec_path": str(remote_spec_path),
            }
        )
        write_launch_summary(local_dir, launch_summary)
        spec_copy = subprocess.run(
            scp_cmd + [str(spec_path), f"root@{pod['ssh']['ip']}:{remote_spec_path}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if spec_copy.returncode != 0:
            stop_pod_quietly(pod_id)
            details = spec_copy.stderr.strip() or spec_copy.stdout.strip() or f"scp exited {spec_copy.returncode}"
            raise LaunchError(
                f"Failed to copy run spec to pod {pod_id}: {details}",
                launch_summary,
            )
        launch_summary["launch_phase"] = "spec_copied"
        write_launch_summary(local_dir, launch_summary)
        extra_env: dict[str, str] = {}
        cache_path = resolve_flash_attn_cache(root, args)
        if cache_path is not None:
            remote_cache_path = Path("/workspace") / cache_path.name
            launch_summary.update(
                {
                    "launch_phase": "copying_flash_attn_cache",
                    "flash_attn_cache_tarball": str(cache_path),
                    "remote_flash_attn_cache_tarball": str(remote_cache_path),
                }
            )
            write_launch_summary(local_dir, launch_summary)
            copy_proc = subprocess.run(
                scp_cmd + [str(cache_path), f"root@{pod['ssh']['ip']}:{remote_cache_path}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if copy_proc.returncode != 0:
                stop_pod_quietly(pod_id)
                details = copy_proc.stderr.strip() or copy_proc.stdout.strip() or f"scp exited {copy_proc.returncode}"
                raise LaunchError(
                    f"Failed to copy FlashAttention cache to pod {pod_id}: {details}",
                    launch_summary,
                )
            extra_env["FLASH_ATTN_CACHE_TARBALL"] = str(remote_cache_path)
            launch_summary["launch_phase"] = "flash_attn_cache_copied"
            write_launch_summary(local_dir, launch_summary)
        remote_command = build_remote_launch_command(
            args.repo_ref,
            str(remote_spec_path),
            args.remote_state_dir,
            spec["run_id"],
            extra_env=extra_env,
        )
        launch_summary["launch_phase"] = "launching_remote_watchdog"
        write_launch_summary(local_dir, launch_summary)
        remote_error = None
        for attempt in range(1, remote_launch_retries + 1):
            try:
                run_text(ssh_cmd + [remote_command])
                remote_error = None
                break
            except subprocess.CalledProcessError as exc:
                remote_error = exc
                if attempt < remote_launch_retries:
                    time.sleep(remote_launch_retry_delay)
                    continue
        if remote_error is not None:
            stop_pod_quietly(pod_id)
            details = remote_error.stderr.strip() or remote_error.stdout.strip() or str(remote_error)
            raise LaunchError(f"Remote watchdog launch failed on pod {pod_id}: {details}", launch_summary) from remote_error

        mirror_log = local_dir / "mirror.log"
        mirror_cmd = build_mirror_command(args, pod_id, local_dir)
        with mirror_log.open("a", encoding="utf-8") as handle:
            proc = subprocess.Popen(
                mirror_cmd,
                stdout=handle,
                stderr=subprocess.STDOUT,
                cwd=str(root),
                start_new_session=True,
                text=True,
            )

        launch_summary.update(
            {
                "mirror_pid": proc.pid,
                "mirror_log": str(mirror_log.resolve()),
                "local_dir": str(local_dir.resolve()),
                "launched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "launch_phase": "active",
            }
        )
        write_launch_summary(local_dir, launch_summary)
        return launch_summary
    except LaunchError as exc:
        if not exc.launch_summary:
            exc.launch_summary = launch_summary
        raise


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    launch_summary = launch_managed_run(args)
    print(json.dumps(launch_summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
