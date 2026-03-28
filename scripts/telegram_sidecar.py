#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACTIVE_RUN_STATUSES = {"launching", "running", "starting", "dry-run"}
TERMINAL_RUN_STATUSES = {"complete", "failed", "dry-run-complete"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def isoformat_mtime(path: Path | None) -> str | None:
    if not path or not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def all_run_dirs(live_root: Path) -> list[Path]:
    if not live_root.exists():
        return []
    return sorted([child for child in live_root.iterdir() if child.is_dir()])


def run_snapshot(run_dir: Path) -> dict[str, Any]:
    budget_state = read_json(run_dir.parent.parent / "control_plane/state/budget_state.json")
    active_pods = {
        str(pod.get("id")): pod
        for pod in (budget_state.get("active_pods") or [])
        if pod.get("id")
    }
    current = read_json(run_dir / "current_state.json")
    terminal = read_json(run_dir / "terminal_result.json")
    launch = read_json(run_dir / "launch.json")
    summary = read_text(run_dir / "summary.md")
    pod_id = launch.get("pod_id")
    active_pod = active_pods.get(str(pod_id)) if pod_id else None
    inferred_run_status = current.get("status")
    if not inferred_run_status and launch and active_pod:
        inferred_run_status = "launching"
    inferred_phase_id = current.get("phase_id")
    if not inferred_phase_id and inferred_run_status in ACTIVE_RUN_STATUSES:
        inferred_phase_id = launch.get("launch_phase")
    return {
        "run_id": run_dir.name,
        "run_status": inferred_run_status,
        "terminal_status": terminal.get("status"),
        "phase_id": inferred_phase_id,
        "updated_at": (
            current.get("updated_at")
            or terminal.get("updated_at")
            or launch.get("launched_at")
            or isoformat_mtime(run_dir / "current_state.json")
            or isoformat_mtime(run_dir / "terminal_result.json")
            or isoformat_mtime(run_dir / "launch.json")
        ),
        "pod_id": pod_id,
        "pod_status": active_pod.get("desiredStatus") if active_pod else None,
        "launch_phase": launch.get("launch_phase"),
        "summary": summary,
    }


def active_snapshot(live_root: Path) -> dict[str, Any] | None:
    snapshots = [run_snapshot(run_dir) for run_dir in all_run_dirs(live_root)]
    active = [snap for snap in snapshots if snap.get("run_status") in ACTIVE_RUN_STATUSES]
    if active:
        active.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return active[0]
    terminal = [snap for snap in snapshots if snap.get("terminal_status") in TERMINAL_RUN_STATUSES]
    if terminal:
        terminal.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return terminal[0]
    return snapshots[-1] if snapshots else None


def short_pod_id(pod_id: str | None) -> str:
    return pod_id[:8] if pod_id else "n/a"


def trim(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def proactive_message(snapshot: dict[str, Any]) -> str:
    lines = ["Parameter Golf Update", f"Run: {snapshot['run_id']}"]
    if snapshot.get("pod_id"):
        lines.append(f"Pod: {short_pod_id(snapshot['pod_id'])}")
    if snapshot.get("pod_status"):
        lines.append(f"Pod status: {snapshot['pod_status']}")
    if snapshot.get("phase_id"):
        lines.append(f"Phase: {snapshot['phase_id']}")
    if snapshot.get("run_status"):
        lines.append(f"Status: {snapshot['run_status']}")
    if snapshot.get("terminal_status") and snapshot.get("terminal_status") != "idle":
        lines.append(f"Terminal: {snapshot['terminal_status']}")
    if snapshot.get("updated_at"):
        lines.append(f"Updated: {snapshot['updated_at']}")
    summary = trim(snapshot.get("summary") or "", 1200)
    if summary:
        lines.extend(["", summary])
    return "\n".join(lines)


def state_key(snapshot: dict[str, Any]) -> str:
    return json.dumps(
        {
            "launch_phase": snapshot.get("launch_phase"),
            "pod_status": snapshot.get("pod_status"),
            "run_status": snapshot.get("run_status"),
            "terminal_status": snapshot.get("terminal_status"),
            "phase_id": snapshot.get("phase_id"),
            "updated_at": snapshot.get("updated_at"),
        },
        sort_keys=True,
    )


def build_live_context(root: Path, live_root: Path) -> str:
    operator_state = read_json(root / "11_RUN_CONTROL/control_plane/state/operator_state.json")
    budget_state = read_json(root / "11_RUN_CONTROL/control_plane/state/budget_state.json")
    queue_state = read_json(root / "11_RUN_CONTROL/control_plane/state/queue.json")
    snapshot = active_snapshot(live_root)

    context = {
        "operator_state": {
            "queue_blocked": operator_state.get("queue_blocked"),
            "queue_blocked_reason": operator_state.get("queue_blocked_reason"),
            "active_pod_count": operator_state.get("active_pod_count"),
            "top_ranked_target": operator_state.get("top_ranked_target"),
            "updated_at": operator_state.get("updated_at"),
        },
        "budget_state": {
            "client_balance": budget_state.get("client_balance"),
            "current_spend_per_hr": budget_state.get("current_spend_per_hr"),
            "reserved_today_usd": budget_state.get("reserved_today_usd"),
            "daily_cap_usd": budget_state.get("daily_cap_usd"),
            "active_pod_count": budget_state.get("active_pod_count"),
            "active_pods": (budget_state.get("active_pods") or [])[:3],
            "updated_at": budget_state.get("updated_at"),
        },
        "queue_state": {
            "blocked": queue_state.get("blocked"),
            "blocked_reason": queue_state.get("blocked_reason"),
            "next_run_id": queue_state.get("next_run_id"),
            "next_target_pr": queue_state.get("next_target_pr"),
            "candidates": (queue_state.get("candidates") or [])[:3],
            "updated_at": queue_state.get("updated_at"),
        },
        "active_or_latest_run": {
            "run_id": snapshot.get("run_id") if snapshot else None,
            "run_status": snapshot.get("run_status") if snapshot else None,
            "terminal_status": snapshot.get("terminal_status") if snapshot else None,
            "phase_id": snapshot.get("phase_id") if snapshot else None,
            "pod_id": snapshot.get("pod_id") if snapshot else None,
            "pod_status": snapshot.get("pod_status") if snapshot else None,
            "launch_phase": snapshot.get("launch_phase") if snapshot else None,
            "updated_at": snapshot.get("updated_at") if snapshot else None,
            "summary_tail": trim(snapshot.get("summary") or "", 2500) if snapshot else "",
        },
    }
    return json.dumps(context, indent=2, sort_keys=True)


def build_prompt(root: Path, live_root: Path, transcript: list[dict[str, str]], user_text: str) -> str:
    live_context = build_live_context(root, live_root)
    return "\n".join(
        [
            "You are Parameter Golf Bot, a conversational gateway for a live autonomous research operator.",
            "Be natural, concise, and useful. Do not sound like a command parser.",
            "Use the live control-plane state below as truth.",
            "If any earlier assistant statement conflicts with the live state, explicitly correct it and trust the live state.",
            "You are not the executor. Do not claim you performed actions unless the live state proves it.",
            "If the user asks for strategy or judgment, answer like a pragmatic operator/CEO.",
            "If the user asks to take an action, you may describe the recommended action, but do not claim it already happened.",
            "If the user asks how things are going, synthesize the current run state and next decision point.",
            "This chat is persistent. Use prior conversation context naturally.",
            "",
            "LIVE STATE",
            live_context,
            "",
            f"NEW USER MESSAGE\nUSER: {user_text}",
            "",
            "Reply as the assistant only.",
        ]
    )


def parse_codex_jsonl(stdout: str) -> tuple[str | None, str | None]:
    thread_id: str | None = None
    reply: str | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "thread.started":
            thread_id = obj.get("thread_id")
        item = obj.get("item") or {}
        if obj.get("type") == "item.completed" and item.get("type") == "agent_message":
            reply = item.get("text") or reply
    return thread_id, reply


def run_codex_turn(root: Path, prompt: str, thread_id: str | None) -> tuple[str, str | None]:
    cmd = [
        "codex",
        "exec",
        "-C",
        str(root),
        "--skip-git-repo-check",
        "-s",
        "read-only",
        "-m",
        "gpt-5.4",
        "--json",
    ]
    if thread_id:
        cmd.extend(["resume", thread_id, prompt])
    else:
        cmd.append(prompt)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=180)
    next_thread_id, reply = parse_codex_jsonl(proc.stdout)
    effective_thread_id = next_thread_id or thread_id
    if not reply:
        raise RuntimeError("codex produced no assistant reply")
    return reply, effective_thread_id


def run_codex_with_retry(root: Path, prompt: str, thread_id: str | None, attempts: int = 2) -> tuple[str, str | None]:
    last_error: Exception | None = None
    current_thread_id = thread_id
    for attempt in range(1, attempts + 1):
        try:
            return run_codex_turn(root, prompt, current_thread_id)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as exc:
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(float(attempt))
    raise last_error if last_error else RuntimeError("unknown codex failure")


def help_message() -> str:
    return "\n".join(
        [
            "Parameter Golf Bot",
            "You can ask naturally now.",
            "",
            "Examples:",
            "- how's it going?",
            "- what is the strategy?",
            "- what should we do next?",
            "- how is the budget looking?",
            "- reset session",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram conversational gateway for Parameter Golf.")
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
    offset = state.get("offset")
    chats = state.get("chats", {})
    threads = state.get("threads", {})
    initialized = bool(state)

    while True:
        snapshots = {snap["run_id"]: snap for snap in [run_snapshot(run_dir) for run_dir in all_run_dirs(live_root)]}
        if not initialized:
            for run_id, snapshot in snapshots.items():
                sent[run_id] = state_key(snapshot)
            initialized = True

        for run_id, snapshot in snapshots.items():
            current_key = state_key(snapshot)
            if sent.get(run_id) != current_key and (snapshot.get("phase_id") or snapshot.get("terminal_status")):
                send_telegram(args.bot_token, args.chat_id, proactive_message(snapshot))
                sent[run_id] = current_key

        for update in get_updates(args.bot_token, offset):
            offset = int(update["update_id"]) + 1
            message = update.get("message") or {}
            chat = message.get("chat") or {}
            chat_id = str(chat.get("id"))
            if chat_id != str(args.chat_id):
                continue
            user_text = (message.get("text") or "").strip()
            if not user_text:
                continue

            transcript = chats.get(chat_id, [])
            thread_id = threads.get(chat_id)
            if user_text.lower() in {"/start", "/help", "help"}:
                reply = help_message()
            elif user_text.lower() in {"reset", "/reset", "new session", "reset session"}:
                threads.pop(chat_id, None)
                chats[chat_id] = []
                reply = "Parameter Golf Bot\nSession reset. Ask naturally again."
            else:
                transcript.append({"role": "user", "text": user_text, "timestamp": utc_now()})
                prompt = build_prompt(root, live_root, transcript, user_text)
                try:
                    reply, next_thread_id = run_codex_with_retry(root, prompt, thread_id)
                    if next_thread_id:
                        threads[chat_id] = next_thread_id
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as exc:
                    reply = "\n".join(
                        [
                            "Parameter Golf Bot",
                            "The conversational backend failed on this turn.",
                            f"Reason: {type(exc).__name__}",
                            "",
                            "Try again in a moment.",
                        ]
                    )
                transcript.append({"role": "assistant", "text": reply, "timestamp": utc_now()})
                chats[chat_id] = transcript[-12:]

            send_telegram(args.bot_token, args.chat_id, reply)

        atomic_write_json(
            state_file,
            {
                "updated_at": utc_now(),
                "offset": offset,
                "sent": sent,
                "chats": chats,
                "threads": threads,
            },
        )
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
