#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = {"complete", "failed", "dry-run-complete"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_json(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


def run_text(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return proc.stdout


def shutil_which(command: str) -> str | None:
    return subprocess.run(
        ["/usr/bin/env", "python3", "-c", f"import shutil; print(shutil.which({command!r}) or '')"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip() or None


def maybe_notify_macos(title: str, body: str) -> None:
    if not shutil_which("osascript"):
        return
    script = f'display notification {json.dumps(body)} with title {json.dumps(title)}'
    subprocess.run(["osascript", "-e", script], check=False)


def maybe_notify_webhook(webhook_url: str | None, title: str, body: str) -> None:
    if not webhook_url:
        return
    payload = json.dumps({"title": title, "body": body}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15):
            pass
    except (urllib.error.URLError, TimeoutError):
        pass


def maybe_notify_telegram(bot_token: str | None, chat_id: str | None, title: str, body: str) -> None:
    if not bot_token or not chat_id:
        return
    text = f"{title}\n{body}"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15):
            pass
    except (urllib.error.URLError, TimeoutError):
        pass


def build_remote_fetch_command(remote_state_dir: str, log_lines: int) -> str:
    return (
        "python3 - <<'PY'\n"
        "import json\n"
        "from pathlib import Path\n"
        f"state_dir = Path({remote_state_dir!r})\n"
        f"log_lines = {log_lines}\n"
        "payload = {}\n"
        "def read_text(name):\n"
        "    path = state_dir / name\n"
        "    if not path.exists():\n"
        "        return ''\n"
        "    return path.read_text(encoding='utf-8', errors='replace')\n"
        "def read_json(name):\n"
        "    text = read_text(name)\n"
        "    if not text.strip():\n"
        "        return {}\n"
        "    try:\n"
        "        return json.loads(text)\n"
        "    except json.JSONDecodeError:\n"
        "        return {'_raw': text}\n"
        "payload['status_txt'] = read_text('status.txt')\n"
        "payload['next_action_txt'] = read_text('next_action.txt')\n"
        "payload['current_state'] = read_json('current_state.json')\n"
        "payload['heartbeat'] = read_json('heartbeat.json')\n"
        "payload['terminal_result'] = read_json('terminal_result.json')\n"
        "active_log = payload['current_state'].get('active_log')\n"
        "if active_log:\n"
        "    path = Path(active_log)\n"
        "    if path.exists():\n"
        "        from collections import deque\n"
        "        with path.open('r', encoding='utf-8', errors='replace') as handle:\n"
        "            lines = list(deque(handle, maxlen=log_lines))\n"
        "        lines = [line.rstrip('\\n') for line in lines]\n"
        "        payload['active_log_tail'] = '\\n'.join(lines) + ('\\n' if lines else '')\n"
        "    else:\n"
        "        payload['active_log_tail'] = ''\n"
        "else:\n"
        "    payload['active_log_tail'] = ''\n"
        "print(json.dumps(payload))\n"
        "PY"
    )


def fetch_remote_bundle(ssh_cmd: list[str], remote_state_dir: str, log_lines: int) -> dict[str, Any]:
    command = build_remote_fetch_command(remote_state_dir, log_lines)
    output = run_text(ssh_cmd + [command])
    return json.loads(output)


def classify_state(pod: dict[str, Any], remote: dict[str, Any] | None, last_error: str) -> str:
    current = (remote or {}).get("current_state") or {}
    terminal = (remote or {}).get("terminal_result") or {}
    pod_status = str(pod.get("desiredStatus", "unknown"))
    run_status = current.get("status")
    terminal_status = terminal.get("status")

    if terminal_status in TERMINAL_STATUSES:
        return f"terminal_{terminal_status}"
    if run_status in TERMINAL_STATUSES:
        return f"terminal_{run_status}"
    if pod_status != "RUNNING":
        if run_status in {"starting", "running", "dry-run", None} and terminal_status not in TERMINAL_STATUSES:
            return "infra_provider_exit"
        return "inactive_without_terminal"
    if last_error and not remote:
        return "ssh_unreachable"
    if run_status in {"starting", "running", "dry-run"}:
        return "active"
    return "unknown"


def build_event_payload(pod: dict[str, Any], remote: dict[str, Any] | None, mirror_state: dict[str, Any]) -> dict[str, Any]:
    current = (remote or {}).get("current_state") or {}
    heartbeat = (remote or {}).get("heartbeat") or {}
    terminal = (remote or {}).get("terminal_result") or {}
    last_output = heartbeat.get("last_output") or []
    return {
        "event": "mirror_state_changed",
        "timestamp": mirror_state["mirrored_at"],
        "pod_id": pod.get("id"),
        "pod_status": pod.get("desiredStatus"),
        "pod_cost_per_hr": pod.get("costPerHr"),
        "run_id": current.get("run_id"),
        "run_status": current.get("status"),
        "phase_id": current.get("phase_id"),
        "updated_at": current.get("updated_at"),
        "classification": mirror_state["classification"],
        "last_error": mirror_state["last_error"],
        "terminal_status": terminal.get("status"),
        "last_output": last_output[-1] if last_output else "",
    }


def event_key(pod: dict[str, Any], remote: dict[str, Any] | None, classification: str, last_error: str) -> str:
    current = (remote or {}).get("current_state") or {}
    heartbeat = (remote or {}).get("heartbeat") or {}
    terminal = (remote or {}).get("terminal_result") or {}
    return json.dumps(
        {
            "pod_status": pod.get("desiredStatus"),
            "run_status": current.get("status"),
            "phase_id": current.get("phase_id"),
            "updated_at": current.get("updated_at"),
            "heartbeat_updated_at": heartbeat.get("updated_at"),
            "terminal_status": terminal.get("status"),
            "classification": classification,
            "last_error": last_error,
        },
        sort_keys=True,
    )


def notification_body(pod: dict[str, Any], remote: dict[str, Any] | None, mirror_state: dict[str, Any]) -> str:
    current = (remote or {}).get("current_state") or {}
    heartbeat = (remote or {}).get("heartbeat") or {}
    last_output = heartbeat.get("last_output") or []
    last_line = last_output[-1] if last_output else "no heartbeat output yet"
    summary_path = f"11_RUN_CONTROL/live/{current.get('run_id') or 'unknown'}/summary.md"
    return "\n".join(
        [
            f"run={current.get('run_id')}",
            f"status={current.get('status')}",
            f"phase={current.get('phase_id')}",
            f"classification={mirror_state['classification']}",
            f"pod={pod.get('id')} ({pod.get('desiredStatus')})",
            f"last={last_line}",
            f"summary={summary_path}",
        ]
    )


def write_mirror_files(local_dir: Path, pod: dict[str, Any], remote: dict[str, Any] | None, mirror_state: dict[str, Any]) -> None:
    atomic_write_json(local_dir / "pod.json", pod)
    atomic_write_json(local_dir / "mirror_state.json", mirror_state)
    if remote is None:
        return
    atomic_write_json(local_dir / "current_state.json", remote.get("current_state") or {})
    atomic_write_json(local_dir / "heartbeat.json", remote.get("heartbeat") or {})
    atomic_write_json(local_dir / "terminal_result.json", remote.get("terminal_result") or {})
    atomic_write_text(local_dir / "status.txt", remote.get("status_txt") or "")
    atomic_write_text(local_dir / "next_action.txt", remote.get("next_action_txt") or "")
    atomic_write_text(local_dir / "active_log.tail.txt", remote.get("active_log_tail") or "")


def build_summary(pod: dict[str, Any], remote: dict[str, Any] | None, mirror_state: dict[str, Any]) -> str:
    current = (remote or {}).get("current_state") or {}
    heartbeat = (remote or {}).get("heartbeat") or {}
    terminal = (remote or {}).get("terminal_result") or {}
    lines = [
        "# Live Run Summary",
        "",
        f"- mirrored_at: `{mirror_state.get('mirrored_at')}`",
        f"- pod_id: `{pod.get('id')}`",
        f"- pod_status: `{pod.get('desiredStatus')}`",
        f"- classification: `{mirror_state.get('classification')}`",
    ]
    cost = pod.get("costPerHr")
    if cost is not None:
        lines.append(f"- pod_cost_per_hr: `${cost}`")
    error = mirror_state.get("last_error")
    if error:
        lines.append(f"- last_error: `{error}`")
    if current:
        lines.extend(
            [
                f"- run_id: `{current.get('run_id')}`",
                f"- run_status: `{current.get('status')}`",
                f"- phase: `{current.get('phase_id')}`",
                f"- updated_at: `{current.get('updated_at')}`",
            ]
        )
    if terminal:
        lines.extend(
            [
                f"- terminal_status: `{terminal.get('status')}`",
                f"- terminal_updated_at: `{terminal.get('updated_at')}`",
            ]
        )

    last_output = heartbeat.get("last_output") or []
    if last_output:
        lines.extend(["", "## Last Output", ""])
        lines.extend([f"- `{line}`" for line in last_output[-10:]])

    log_tail = (remote or {}).get("active_log_tail", "").strip()
    if log_tail:
        lines.extend(["", "## Active Log Tail", "", "```text", log_tail, "```"])

    next_action = ((remote or {}).get("next_action_txt") or "").strip()
    if next_action:
        lines.extend(["", "## Next Action", "", "```text", next_action, "```"])
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mirror RunPod watchdog state to local files and optional notifications.")
    parser.add_argument("--pod-id", required=True)
    parser.add_argument("--remote-state-dir", default="/workspace/run_control")
    parser.add_argument("--local-dir", required=True)
    parser.add_argument("--interval", type=float, default=15.0)
    parser.add_argument("--log-lines", type=int, default=120)
    parser.add_argument("--notify-macos", action="store_true")
    parser.add_argument("--webhook-url", default=os.environ.get("RUN_NOTIFY_WEBHOOK_URL"))
    parser.add_argument("--telegram-bot-token", default=os.environ.get("TELEGRAM_BOT_TOKEN"))
    parser.add_argument("--telegram-chat-id", default=os.environ.get("TELEGRAM_CHAT_ID"))
    parser.add_argument("--exit-when-inactive", action=argparse.BooleanOptionalAction, default=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    local_dir = Path(args.local_dir).resolve()
    local_dir.mkdir(parents=True, exist_ok=True)
    mirror_state_path = local_dir / "mirror_state.json"
    event_history_path = local_dir / "events.jsonl"
    prior_state: dict[str, Any] = {}
    if mirror_state_path.exists():
        try:
            prior_state = read_json(mirror_state_path)
        except json.JSONDecodeError:
            prior_state = {}

    while True:
        pod = run_json(["runpodctl", "pod", "get", args.pod_id])
        remote: dict[str, Any] | None = None
        last_error = ""
        desired_status = str(pod.get("desiredStatus"))
        ssh_info = pod.get("ssh") or {}

        if desired_status == "RUNNING" and "ip" in ssh_info and "port" in ssh_info:
            ssh_cmd = [
                "ssh",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-i",
                str(ssh_info["ssh_key"]["path"]),
                f"root@{ssh_info['ip']}",
                "-p",
                str(ssh_info["port"]),
            ]
            try:
                remote = fetch_remote_bundle(ssh_cmd, args.remote_state_dir, args.log_lines)
            except subprocess.CalledProcessError as exc:
                last_error = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        else:
            last_error = ssh_info.get("error", "") if isinstance(ssh_info, dict) else ""

        classification = classify_state(pod, remote, last_error)
        mirror_state = {
            "mirrored_at": utc_now(),
            "pod_status": desired_status,
            "last_error": last_error,
            "classification": classification,
            "event_key": event_key(pod, remote, classification, last_error),
        }
        write_mirror_files(local_dir, pod, remote, mirror_state)
        atomic_write_text(local_dir / "summary.md", build_summary(pod, remote, mirror_state))

        previous_key = prior_state.get("event_key")
        if mirror_state["event_key"] != previous_key:
            event_payload = build_event_payload(pod, remote, mirror_state)
            append_jsonl(event_history_path, event_payload)
            current = (remote or {}).get("current_state") or {}
            title = f"RunPod {args.pod_id}: {mirror_state['classification']}"
            body = notification_body(pod, remote, mirror_state)
            if args.notify_macos:
                maybe_notify_macos(title, body)
            maybe_notify_webhook(args.webhook_url, title, body)
            maybe_notify_telegram(args.telegram_bot_token, args.telegram_chat_id, title, body)
        prior_state = mirror_state

        if args.exit_when_inactive and desired_status != "RUNNING":
            break
        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    sys.exit(main())
