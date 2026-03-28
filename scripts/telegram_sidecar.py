#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STEP_RE = re.compile(r"step:(\d+)/(\d+)")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text[:3800]}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20):
        pass


def latest_step(active_log_tail: str) -> tuple[int | None, int | None]:
    latest: tuple[int | None, int | None] = (None, None)
    for match in STEP_RE.finditer(active_log_tail):
        latest = (int(match.group(1)), int(match.group(2)))
    return latest


def run_snapshot(run_dir: Path) -> dict[str, Any]:
    current = read_json(run_dir / "current_state.json")
    terminal = read_json(run_dir / "terminal_result.json")
    launch = read_json(run_dir / "launch.json")
    summary = (run_dir / "summary.md").read_text(encoding="utf-8") if (run_dir / "summary.md").exists() else ""
    tail = (run_dir / "active_log.tail.txt").read_text(encoding="utf-8") if (run_dir / "active_log.tail.txt").exists() else ""
    step, total = latest_step(tail or summary)
    return {
        "run_id": run_dir.name,
        "phase_id": current.get("phase_id"),
        "run_status": current.get("status"),
        "terminal_status": terminal.get("status"),
        "pod_id": launch.get("pod_id"),
        "step": step,
        "step_total": total,
        "updated_at": current.get("updated_at") or terminal.get("updated_at") or launch.get("launched_at"),
    }


def build_run_message(snapshot: dict[str, Any], reason: str) -> str:
    lines = [f"Parameter Golf {reason}", f"run={snapshot['run_id']}"]
    if snapshot.get("pod_id"):
        lines.append(f"pod={snapshot['pod_id']}")
    if snapshot.get("phase_id"):
        lines.append(f"phase={snapshot['phase_id']}")
    if snapshot.get("run_status"):
        lines.append(f"status={snapshot['run_status']}")
    if snapshot.get("terminal_status"):
        lines.append(f"terminal={snapshot['terminal_status']}")
    if snapshot.get("step") is not None and snapshot.get("step_total") is not None:
        lines.append(f"step={snapshot['step']}/{snapshot['step_total']}")
    if snapshot.get("updated_at"):
        lines.append(f"updated={snapshot['updated_at']}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram notifier sidecar for Parameter Golf.")
    parser.add_argument("--bot-token", required=True)
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--live-root", default="11_RUN_CONTROL/live")
    parser.add_argument("--state-file", default="11_RUN_CONTROL/control_plane/state/telegram_sidecar_state.json")
    parser.add_argument("--poll-interval", type=float, default=15.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(__file__).resolve().parent.parent
    live_root = (root / args.live_root).resolve()
    state_file = (root / args.state_file).resolve()
    state = read_json(state_file)
    sent = state.get("sent", {})
    milestones = state.get("milestones", {})

    while True:
        for run_dir in sorted(live_root.iterdir()) if live_root.exists() else []:
            if not run_dir.is_dir():
                continue
            snapshot = run_snapshot(run_dir)
            run_id = snapshot["run_id"]
            current_key = json.dumps(
                {
                    "phase_id": snapshot.get("phase_id"),
                    "run_status": snapshot.get("run_status"),
                    "terminal_status": snapshot.get("terminal_status"),
                },
                sort_keys=True,
            )
            if sent.get(run_id) != current_key and (snapshot.get("phase_id") or snapshot.get("terminal_status")):
                send_telegram(args.bot_token, args.chat_id, build_run_message(snapshot, "state update"))
                sent[run_id] = current_key

            step = snapshot.get("step")
            if step is not None:
                prior = int(milestones.get(run_id, 0))
                for threshold in (50, 100, 150, 200):
                    if step >= threshold > prior:
                        send_telegram(args.bot_token, args.chat_id, build_run_message(snapshot, f"milestone {threshold}"))
                        milestones[run_id] = threshold

        atomic_write_json(
            state_file,
            {
                "updated_at": utc_now(),
                "sent": sent,
                "milestones": milestones,
            },
        )
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
