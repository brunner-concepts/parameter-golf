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
BPB_RE = re.compile(r"val_bpb:([0-9.]+)")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def telegram_request(bot_token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/{method}",
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    telegram_request(bot_token, "sendMessage", {"chat_id": chat_id, "text": text[:3800]})


def get_updates(bot_token: str, offset: int | None) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {"timeout": 0}
    if offset is not None:
        payload["offset"] = offset
    response = telegram_request(bot_token, "getUpdates", payload)
    return response.get("result", [])


def latest_step(text: str) -> tuple[int | None, int | None]:
    latest: tuple[int | None, int | None] = (None, None)
    for match in STEP_RE.finditer(text):
        latest = (int(match.group(1)), int(match.group(2)))
    return latest


def latest_bpb(text: str) -> str | None:
    latest: str | None = None
    for match in BPB_RE.finditer(text):
        latest = match.group(1)
    return latest


def run_snapshot(run_dir: Path) -> dict[str, Any]:
    current = read_json(run_dir / "current_state.json")
    terminal = read_json(run_dir / "terminal_result.json")
    launch = read_json(run_dir / "launch.json")
    summary = read_text(run_dir / "summary.md")
    tail = read_text(run_dir / "active_log.tail.txt")
    merged_text = tail or summary
    step, total = latest_step(merged_text)
    return {
        "run_id": run_dir.name,
        "phase_id": current.get("phase_id"),
        "run_status": current.get("status"),
        "terminal_status": terminal.get("status"),
        "terminal_message": terminal.get("message"),
        "pod_id": launch.get("pod_id"),
        "gpu_id": launch.get("gpu_id"),
        "step": step,
        "step_total": total,
        "val_bpb": latest_bpb(merged_text),
        "updated_at": current.get("updated_at") or terminal.get("updated_at") or launch.get("launched_at"),
        "summary": summary,
    }


def all_run_snapshots(live_root: Path) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    if not live_root.exists():
        return snapshots
    for run_dir in sorted(live_root.iterdir()):
        if run_dir.is_dir():
            snapshots.append(run_snapshot(run_dir))
    return snapshots


def active_snapshot(live_root: Path) -> dict[str, Any] | None:
    snapshots = all_run_snapshots(live_root)
    active = [s for s in snapshots if s.get("run_status") in {"running", "starting", "dry-run"}]
    if active:
        active.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
        return active[0]
    completed = [s for s in snapshots if s.get("terminal_status") in {"complete", "failed", "dry-run-complete"}]
    if completed:
        completed.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
        return completed[0]
    return snapshots[-1] if snapshots else None


def short_pod_id(pod_id: str | None) -> str:
    if not pod_id:
        return "n/a"
    return pod_id[:8]


def status_message(snapshot: dict[str, Any] | None) -> str:
    if not snapshot:
        return "Parameter Golf\nNo active run."
    lines = [
        "Parameter Golf Status",
        f"Run: {snapshot['run_id']}",
    ]
    if snapshot.get("pod_id"):
        lines.append(f"Pod: {short_pod_id(snapshot['pod_id'])}")
    if snapshot.get("phase_id"):
        lines.append(f"Phase: {snapshot['phase_id']}")
    if snapshot.get("run_status"):
        lines.append(f"Status: {snapshot['run_status']}")
    if snapshot.get("terminal_status") and snapshot.get("terminal_status") != "idle":
        lines.append(f"Terminal: {snapshot['terminal_status']}")
    if snapshot.get("step") is not None and snapshot.get("step_total") is not None:
        lines.append(f"Progress: {snapshot['step']}/{snapshot['step_total']}")
    if snapshot.get("val_bpb"):
        lines.append(f"Latest BPB: {snapshot['val_bpb']}")
    if snapshot.get("updated_at"):
        lines.append(f"Updated: {snapshot['updated_at']}")
    return "\n".join(lines)


def strategy_message(root: Path, live_root: Path) -> str:
    queue = read_json(root / "11_RUN_CONTROL/control_plane/state/queue.json")
    snapshot = active_snapshot(live_root)
    top = (queue.get("candidates") or [{}])[0]
    lines = ["Parameter Golf Strategy"]
    if top.get("pr"):
        lines.append(f"Primary target: PR #{top['pr']} ({top.get('label', 'unknown')})")
        lines.append(f"Why: {top.get('notes', 'highest ranked target in current policy')}")
    if snapshot:
        lines.append(f"Current run: {snapshot['run_id']} on {snapshot.get('phase_id') or 'unknown'}")
    if queue.get("blocked"):
        lines.append(f"Queue: blocked by {queue.get('blocked_reason')}")
    else:
        lines.append("Queue: healthy")
    lines.append("Next gate: if PR #868 smoke completes cleanly, promote to full 8x repro.")
    lines.append("Deferred: PR #933 remains manual-only due legality scrutiny.")
    return "\n".join(lines)


def next_message(root: Path, live_root: Path) -> str:
    snapshot = active_snapshot(live_root)
    if snapshot and snapshot.get("run_status") in {"running", "starting", "dry-run"}:
        return "\n".join(
            [
                "Parameter Golf Next",
                f"Current run is active: {snapshot['run_id']}",
                f"Phase: {snapshot.get('phase_id') or 'unknown'}",
                "Immediate next action: let the run finish and evaluate the terminal result.",
            ]
        )
    queue = read_json(root / "11_RUN_CONTROL/control_plane/state/queue.json")
    if queue.get("next_run_id"):
        return "\n".join(
            [
                "Parameter Golf Next",
                f"Next queued run: {queue['next_run_id']}",
                f"Spec: {queue.get('next_spec')}",
            ]
        )
    return "Parameter Golf Next\nNo queued run right now."


def budget_message(root: Path) -> str:
    budget = read_json(root / "11_RUN_CONTROL/control_plane/state/budget_state.json")
    if not budget:
        return "Parameter Golf Budget\nNo budget snapshot available."
    lines = [
        "Parameter Golf Budget",
        f"Balance: ${budget.get('client_balance', 0):.2f}",
        f"Spend/hr: ${budget.get('current_spend_per_hr', 0):.2f}",
        f"Active pods: {budget.get('active_pod_count', 0)}",
        f"Reserved today: ${budget.get('reserved_today_usd', 0):.2f}",
        f"Daily cap: ${budget.get('daily_cap_usd', 0):.2f}",
    ]
    return "\n".join(lines)


def help_message() -> str:
    return "\n".join(
        [
            "Parameter Golf Bot",
            "Commands:",
            "status - current run and progress",
            "strategy - current target and why",
            "next - next action/gate",
            "budget - RunPod balance and cap",
            "help - this message",
        ]
    )


def classify_query(text: str) -> str:
    normalized = text.strip().lower()
    if normalized in {"/start", "/help", "help"}:
        return "help"
    if normalized in {"/status", "status"} or ("how" in normalized and "going" in normalized):
        return "status"
    if normalized in {"/strategy", "strategy", "plan"} or "strategy" in normalized:
        return "strategy"
    if normalized in {"/next", "next"}:
        return "next"
    if normalized in {"/budget", "budget"}:
        return "budget"
    return "unknown"


def state_key(snapshot: dict[str, Any]) -> str:
    return json.dumps(
        {
            "phase_id": snapshot.get("phase_id"),
            "run_status": snapshot.get("run_status"),
            "terminal_status": snapshot.get("terminal_status"),
            "val_bpb": snapshot.get("val_bpb"),
        },
        sort_keys=True,
    )


def proactive_message(snapshot: dict[str, Any], reason: str) -> str:
    lines = [f"Parameter Golf {reason}"]
    lines.extend(status_message(snapshot).splitlines()[1:])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram gateway sidecar for Parameter Golf.")
    parser.add_argument("--bot-token", required=True)
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--live-root", default="11_RUN_CONTROL/live")
    parser.add_argument("--state-file", default="11_RUN_CONTROL/control_plane/state/telegram_sidecar_state.json")
    parser.add_argument("--poll-interval", type=float, default=10.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(__file__).resolve().parent.parent
    live_root = (root / args.live_root).resolve()
    state_file = (root / args.state_file).resolve()
    state = read_json(state_file)
    sent = state.get("sent", {})
    milestones = state.get("milestones", {})
    offset = state.get("offset")
    initialized = bool(state)

    while True:
        snapshots = {snap["run_id"]: snap for snap in all_run_snapshots(live_root)}

        if not initialized:
            for run_id, snapshot in snapshots.items():
                sent[run_id] = state_key(snapshot)
                step = snapshot.get("step")
                if step is not None:
                    if step >= 200:
                        milestones[run_id] = 200
                    elif step >= 150:
                        milestones[run_id] = 150
                    elif step >= 100:
                        milestones[run_id] = 100
                    elif step >= 50:
                        milestones[run_id] = 50
            initialized = True

        for run_id, snapshot in snapshots.items():
            current_key = state_key(snapshot)
            previous_key = sent.get(run_id)
            if previous_key != current_key and (snapshot.get("phase_id") or snapshot.get("terminal_status")):
                send_telegram(args.bot_token, args.chat_id, proactive_message(snapshot, "update"))
                sent[run_id] = current_key

            step = snapshot.get("step")
            if step is not None:
                prior = int(milestones.get(run_id, 0))
                crossed = [threshold for threshold in (50, 100, 150, 200) if step >= threshold > prior]
                if crossed:
                    threshold = max(crossed)
                    send_telegram(args.bot_token, args.chat_id, proactive_message(snapshot, f"milestone {threshold}"))
                    milestones[run_id] = threshold

        for update in get_updates(args.bot_token, offset):
            offset = int(update["update_id"]) + 1
            message = update.get("message") or {}
            chat = message.get("chat") or {}
            if str(chat.get("id")) != str(args.chat_id):
                continue
            text = (message.get("text") or "").strip()
            query = classify_query(text)
            if query == "help":
                reply = help_message()
            elif query == "status":
                reply = status_message(active_snapshot(live_root))
            elif query == "strategy":
                reply = strategy_message(root, live_root)
            elif query == "next":
                reply = next_message(root, live_root)
            elif query == "budget":
                reply = budget_message(root)
            else:
                reply = "\n".join(
                    [
                        "Parameter Golf Bot",
                        "Use: status, strategy, next, budget, help",
                    ]
                )
            send_telegram(args.bot_token, args.chat_id, reply)

        atomic_write_json(
            state_file,
            {
                "updated_at": utc_now(),
                "offset": offset,
                "sent": sent,
                "milestones": milestones,
            },
        )
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
