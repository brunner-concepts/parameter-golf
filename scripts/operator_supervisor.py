#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import launch_runpod_managed_run as launcher


TERMINAL_STATUSES = {"complete", "failed", "dry-run-complete"}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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


def load_spec(spec_path: Path) -> dict[str, Any]:
    return json.loads(spec_path.read_text(encoding="utf-8"))


def classify_live_outcome(local_dir: Path) -> dict[str, Any]:
    mirror_state = read_json_if_exists(local_dir / "mirror_state.json")
    terminal_result = read_json_if_exists(local_dir / "terminal_result.json")
    current_state = read_json_if_exists(local_dir / "current_state.json")
    launch_summary = read_json_if_exists(local_dir / "launch.json")

    terminal_status = terminal_result.get("status")
    if terminal_status in {"complete", "dry-run-complete"}:
        return {
            "outcome": "success",
            "terminal_status": terminal_status,
            "classification": mirror_state.get("classification"),
            "pod_id": launch_summary.get("pod_id"),
        }
    if terminal_status == "failed":
        return {
            "outcome": "failed",
            "terminal_status": terminal_status,
            "classification": mirror_state.get("classification"),
            "pod_id": launch_summary.get("pod_id"),
        }

    classification = mirror_state.get("classification")
    pod_status = mirror_state.get("pod_status")
    if classification == "infra_provider_exit":
        return {
            "outcome": "infra_failure",
            "terminal_status": terminal_status,
            "classification": classification,
            "pod_id": launch_summary.get("pod_id"),
        }
    if pod_status and pod_status != "RUNNING" and current_state.get("status") not in TERMINAL_STATUSES:
        return {
            "outcome": "infra_failure",
            "terminal_status": terminal_status,
            "classification": classification or "inactive_without_terminal",
            "pod_id": launch_summary.get("pod_id"),
        }

    return {
        "outcome": "active",
        "terminal_status": terminal_status,
        "classification": classification,
        "pod_id": launch_summary.get("pod_id"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guardrailed supervisor for a single approved RunPod spec.")
    parser.add_argument("spec", help="Path to the run spec to execute.")
    parser.add_argument("--max-infra-retries", type=int, default=1)
    parser.add_argument("--poll-interval", type=float, default=15.0)
    parser.add_argument("--template-id", default=launcher.DEFAULT_TEMPLATE_ID)
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
    parser.add_argument("--ssh-setup-timeout", type=int, default=60)
    parser.add_argument("--spec-copy-timeout", type=int, default=120)
    parser.add_argument("--flash-attn-cache-copy-timeout", type=int, default=480)
    parser.add_argument("--remote-launch-timeout", type=int, default=180)
    parser.add_argument("--flash-attn-cache-tarball")
    parser.add_argument("--min-balance", type=float)
    parser.add_argument("--notify-macos", action="store_true")
    parser.add_argument("--webhook-url")
    parser.add_argument("--telegram-bot-token")
    parser.add_argument("--telegram-chat-id")
    parser.add_argument("--mirror-exit-when-inactive", action=argparse.BooleanOptionalAction, default=True)
    return parser


def notify_retry_event(local_dir: Path, attempt: int, classification: str, pod_id: str | None) -> None:
    append_jsonl(
        local_dir / "supervisor_events.jsonl",
        {
            "event": "infra_retry_scheduled",
            "timestamp": utc_now(),
            "attempt": attempt,
            "classification": classification,
            "pod_id": pod_id,
        },
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    spec_path = Path(args.spec).resolve()
    spec = load_spec(spec_path)
    root = launcher.repo_root()
    local_dir = root / "11_RUN_CONTROL" / "live" / spec["run_id"]
    local_dir.mkdir(parents=True, exist_ok=True)
    supervisor_state_path = local_dir / "supervisor_state.json"

    attempt = 0
    while True:
        attempt += 1
        atomic_write_json(
            supervisor_state_path,
            {
                "updated_at": utc_now(),
                "run_id": spec["run_id"],
                "attempt": attempt,
                "max_infra_retries": args.max_infra_retries,
                "status": "launching",
            },
        )
        append_jsonl(
            local_dir / "supervisor_events.jsonl",
            {
                "event": "launch_attempt_started",
                "timestamp": utc_now(),
                "attempt": attempt,
                "spec_path": str(spec_path),
            },
        )

        try:
            launch_summary = launcher.launch_managed_run(args)
        except launcher.LaunchError as exc:
            launch_summary = exc.launch_summary
            append_jsonl(
                local_dir / "supervisor_events.jsonl",
                {
                    "event": "launch_attempt_failed",
                    "timestamp": utc_now(),
                    "attempt": attempt,
                    "error": str(exc),
                    "launch_summary": launch_summary,
                },
            )
            if attempt <= args.max_infra_retries:
                notify_retry_event(local_dir, attempt, "launch_failure", launch_summary.get("pod_id"))
                continue
            atomic_write_json(
                supervisor_state_path,
                {
                    "updated_at": utc_now(),
                    "run_id": spec["run_id"],
                    "attempt": attempt,
                    "status": "failed",
                    "failure": str(exc),
                },
            )
            sys.stderr.write(f"{exc}\n")
            return 1

        append_jsonl(
            local_dir / "supervisor_events.jsonl",
            {
                "event": "launch_attempt_active",
                "timestamp": utc_now(),
                "attempt": attempt,
                "launch_summary": launch_summary,
            },
        )

        while True:
            outcome = classify_live_outcome(local_dir)
            atomic_write_json(
                supervisor_state_path,
                {
                    "updated_at": utc_now(),
                    "run_id": spec["run_id"],
                    "attempt": attempt,
                    "max_infra_retries": args.max_infra_retries,
                    "status": "watching",
                    "outcome": outcome,
                },
            )
            if outcome["outcome"] != "active":
                break
            time.sleep(args.poll_interval)

        append_jsonl(
            local_dir / "supervisor_events.jsonl",
            {
                "event": "launch_attempt_finished",
                "timestamp": utc_now(),
                "attempt": attempt,
                "outcome": outcome,
            },
        )

        if outcome["outcome"] == "success":
            atomic_write_json(
                supervisor_state_path,
                {
                    "updated_at": utc_now(),
                    "run_id": spec["run_id"],
                    "attempt": attempt,
                    "status": "complete",
                    "outcome": outcome,
                },
            )
            return 0

        if outcome["outcome"] == "infra_failure" and attempt <= args.max_infra_retries:
            notify_retry_event(local_dir, attempt, outcome["classification"], outcome.get("pod_id"))
            continue

        atomic_write_json(
            supervisor_state_path,
            {
                "updated_at": utc_now(),
                "run_id": spec["run_id"],
                "attempt": attempt,
                "status": "failed",
                "outcome": outcome,
            },
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
