#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


API_ROOT = "https://api.github.com/repos/openai/parameter-golf"
USER_AGENT = "openai-project-golf-control-plane/1.0"
ACTIVE_RUN_STATUSES = {"starting", "running", "dry-run"}
COST_ESTIMATES = {
    "1xH100-smoke": 2.39,
    "8xH100-SXM": 21.52,
}


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


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def run_json(cmd: list[str]) -> Any:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)


def run_subprocess(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=True)


def github_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )


def fetch_issue(issue_number: int) -> dict[str, Any]:
    with urllib.request.urlopen(github_request(f"{API_ROOT}/issues/{issue_number}"), timeout=30) as response:
        issue = json.load(response)
    body = issue.get("body") or ""
    body = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", body)
    body = body.split("![Best Pending BPB Over Time]", 1)[0].strip()
    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "html_url": issue.get("html_url"),
        "updated_at": issue.get("updated_at"),
        "state": issue.get("state"),
        "body_excerpt": body[:1200],
    }


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def score_margin(claimed_bpb: float | None, official_sota_bpb: float) -> float:
    if claimed_bpb is None or claimed_bpb <= 0:
        return 0.0
    return max(0.0, min(1.0, (official_sota_bpb - claimed_bpb) / official_sota_bpb))


def load_manifest_targets(manifest: dict[str, Any]) -> dict[int, dict[str, Any]]:
    targets: dict[int, dict[str, Any]] = {}
    for item in manifest.get("targets", []):
        pr_number = int(item["pr"])
        targets[pr_number] = item
    return targets


def rank_targets(policy: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    weights = policy["ranking_weights"]
    official_sota_bpb = float(policy["frontier"]["official_sota_bpb"])
    manifest_targets = load_manifest_targets(manifest)
    ranked: list[dict[str, Any]] = []
    for key, target_policy in policy.get("targets", {}).items():
        pr_number = int(key)
        meta = manifest_targets.get(pr_number, {})
        claimed = meta.get("claimed_bpb", {}).get("value")
        margin_score = score_margin(float(claimed), official_sota_bpb) if claimed is not None else 0.0
        total = (
            float(target_policy["acceptance_safety"]) * float(weights["acceptance_safety"])
            + float(target_policy["reproducibility"]) * float(weights["reproducibility"])
            + float(target_policy["cost_inverse"]) * float(weights["cost_inverse"])
            + margin_score * float(weights["score_margin"])
        )
        ranked.append(
            {
                "pr": pr_number,
                "label": target_policy["label"],
                "priority": int(target_policy["priority"]),
                "auto_run": bool(target_policy["auto_run"]),
                "legality_risk": target_policy["legality_risk"],
                "notes": target_policy["notes"],
                "acceptance_safety": float(target_policy["acceptance_safety"]),
                "reproducibility": float(target_policy["reproducibility"]),
                "cost_inverse": float(target_policy["cost_inverse"]),
                "claimed_bpb": claimed,
                "claimed_bpb_source": meta.get("claimed_bpb", {}).get("source"),
                "html_url": meta.get("html_url"),
                "head_sha": meta.get("head_sha"),
                "score_margin": margin_score,
                "ranking_score": round(total, 6),
            }
        )
    ranked.sort(key=lambda item: (-item["ranking_score"], item["priority"], item["pr"]))
    return ranked


def write_legality_memos(
    advisory_root: Path,
    ranked_targets: list[dict[str, Any]],
    issue: dict[str, Any],
) -> None:
    ensure_dirs(advisory_root)
    issue_excerpt = issue.get("body_excerpt", "").strip()
    index_lines = ["# Advisory Index", "", f"- generated_at: `{utc_now()}`", ""]
    for target in ranked_targets:
        memo_path = advisory_root / f"pr{target['pr']}_memo.md"
        lines = [
            f"# PR #{target['pr']} Advisory Memo",
            "",
            f"- ranking_score: `{target['ranking_score']}`",
            f"- claimed_bpb: `{target['claimed_bpb']}`",
            f"- acceptance_safety: `{target['acceptance_safety']}`",
            f"- reproducibility: `{target['reproducibility']}`",
            f"- legality_risk: `{target['legality_risk']}`",
            f"- auto_run: `{target['auto_run']}`",
            f"- source: `{target.get('claimed_bpb_source')}`",
            "",
            "## Operator View",
            "",
            target["notes"],
        ]
        if target.get("html_url"):
            lines.extend(["", f"Upstream: {target['html_url']}"])
        if issue_excerpt:
            lines.extend(["", "## Frontier Tracker Excerpt", "", issue_excerpt])
        atomic_write_text(memo_path, "\n".join(lines).strip() + "\n")
        index_lines.append(f"- [PR #{target['pr']} memo]({memo_path.name})")
    atomic_write_text(advisory_root / "README.md", "\n".join(index_lines).strip() + "\n")


def sync_frontier(
    policy: dict[str, Any],
    control_root: Path,
    state_root: Path,
    events_path: Path,
) -> dict[str, Any]:
    upstream_root = control_root / "upstream_prs"
    manifest_path = upstream_root / "manifest.json"
    ensure_dirs(upstream_root)
    sync_cmd = [
        sys.executable,
        str(repo_root() / "scripts" / "sync_repro_targets.py"),
        "--out-dir",
        str(upstream_root),
        "--manifest",
        str(manifest_path),
    ]
    sync_result = run_subprocess(sync_cmd, cwd=repo_root())
    issue = fetch_issue(int(policy["frontier"]["issue_number"]))
    manifest = read_json_if_exists(manifest_path)
    ranked_targets = rank_targets(policy, manifest)
    advisory_root = control_root / "advisory"
    write_legality_memos(advisory_root, ranked_targets, issue)
    snapshot = {
        "updated_at": utc_now(),
        "issue": issue,
        "sync_stdout": sync_result.stdout.strip(),
        "sync_stderr": sync_result.stderr.strip(),
        "manifest_path": str(manifest_path),
        "targets": ranked_targets,
    }
    atomic_write_json(state_root / "frontier_snapshot.json", snapshot)
    append_jsonl(
        events_path,
        {
            "event": "frontier_synced",
            "timestamp": snapshot["updated_at"],
            "top_target": ranked_targets[0]["pr"] if ranked_targets else None,
        },
    )
    return snapshot


def refresh_budget(
    policy: dict[str, Any],
    state_root: Path,
    events_path: Path,
) -> dict[str, Any]:
    user = run_json(["runpodctl", "user"])
    pods = run_json(["runpodctl", "pod", "list", "--all"])
    running_pods = [pod for pod in pods if str(pod.get("desiredStatus")) == "RUNNING"]
    launch_events = read_jsonl(state_root / "launch_events.jsonl")
    today = datetime.now(timezone.utc).date().isoformat()
    reserved_today = sum(
        float(event.get("reserve_usd", 0.0))
        for event in launch_events
        if str(event.get("timestamp", "")).startswith(today)
    )
    budget_state = {
        "updated_at": utc_now(),
        "client_balance": float(user["clientBalance"]),
        "spend_limit_per_hr": float(user.get("spendLimit", 0.0)),
        "current_spend_per_hr": float(user.get("currentSpendPerHr", 0.0)),
        "active_pod_count": len(running_pods),
        "active_pods": running_pods,
        "reserved_today_usd": round(reserved_today, 4),
        "daily_cap_usd": float(policy["daily_caps"]["runpod_usd"]),
        "minimum_runpod_balance_reserve_usd": float(policy["daily_caps"]["minimum_runpod_balance_reserve_usd"]),
    }
    atomic_write_json(state_root / "budget_state.json", budget_state)
    append_jsonl(
        events_path,
        {
            "event": "budget_refreshed",
            "timestamp": budget_state["updated_at"],
            "client_balance": budget_state["client_balance"],
            "active_pod_count": budget_state["active_pod_count"],
            "reserved_today_usd": budget_state["reserved_today_usd"],
        },
    )
    return budget_state


def live_run_snapshot(live_root: Path, run_id: str) -> dict[str, Any]:
    run_dir = live_root / run_id
    if not run_dir.exists():
        return {}
    current_state = read_json_if_exists(run_dir / "current_state.json")
    terminal_result = read_json_if_exists(run_dir / "terminal_result.json")
    supervisor = read_json_if_exists(run_dir / "supervisor_state.json")
    mirror = read_json_if_exists(run_dir / "mirror_state.json")
    pod = read_json_if_exists(run_dir / "pod.json")
    return {
        "run_id": run_id,
        "current_state": current_state,
        "terminal_result": terminal_result,
        "supervisor_state": supervisor,
        "mirror_state": mirror,
        "pod": pod,
    }


def any_active_live_run(live_root: Path) -> list[dict[str, Any]]:
    active_runs: list[dict[str, Any]] = []
    if not live_root.exists():
        return active_runs
    for child in sorted(live_root.iterdir()):
        if not child.is_dir():
            continue
        current_state = read_json_if_exists(child / "current_state.json")
        status = current_state.get("status")
        if status in ACTIVE_RUN_STATUSES:
            active_runs.append(
                {
                    "run_id": child.name,
                    "status": status,
                    "phase_id": current_state.get("phase_id"),
                    "updated_at": current_state.get("updated_at"),
                }
            )
    return active_runs


def common_spec_env() -> dict[str, str]:
    return {
        "REPO_URL": "https://github.com/brunner-concepts/parameter-golf.git",
        "CHECKOUT_REF": "main",
        "REPO_DIR": "/workspace/parameter-golf",
        "VENV_DIR": "/workspace/pgolf-venv",
        "FLASH_ATTN_ROOT": "/workspace/flash-attention",
        "FLASH_ATTN_REF": "6362bd3bcad059aa15fd993c6a9d5d1ee8a11418",
        "FLASH_ATTN_MODE": "auto",
        "MAX_JOBS": "8",
        "DATA_VARIANT": "sp1024",
    }


def build_pr868_specs(generated_root: Path) -> dict[str, Path]:
    ensure_dirs(generated_root)
    smoke_path = generated_root / "repro_pr868_smoke.json"
    full_path = generated_root / "repro_pr868_full.json"
    env = {
        **common_spec_env(),
        "UPSTREAM_RECORD_DIR": "third_party/upstream_prs/pr868",
        "UPSTREAM_REQUIREMENTS": "${REPO_DIR}/third_party/upstream_prs/pr868/requirements.txt",
        "RUN_ENTRYPOINT": "train_gpt.py",
    }
    smoke_spec = {
        "schema_version": 1,
        "run_id": "repro_pr868_smoke",
        "hypothesis": "Validate the conservative PR #868 budgeted two-pass n-gram cache path on 1x H100 PCIe before spending on the full 8x reproduction.",
        "parent_branch": "repro/pr868",
        "track": "cache",
        "compute_tier": "1xH100-smoke",
        "auto_promote": False,
        "promotion_gate": "Smoke must complete cleanly before the daemon may spend on the full 8x H100 SXM PR #868 reproduction.",
        "env": env,
        "phases": [
            {
                "id": "bootstrap_env",
                "description": "Prepare the repo, virtualenv, zstandard, and flash_attn_interface for the upstream cache reproduction path.",
                "command": "bash scripts/bootstrap_runpod_env.sh",
                "cwd": "${REPO_DIR}",
                "log_name": "bootstrap_env.log",
                "failure_summary": "Fix the cache-route bootstrap failure on the smoke tier before spending more compute.",
            },
            {
                "id": "install_requirements",
                "description": "Install any PR-specific Python requirements before running the upstream record path.",
                "command": "bash scripts/install_upstream_requirements.sh",
                "cwd": "${REPO_DIR}",
                "log_name": "install_requirements.log",
                "failure_summary": "Fix the upstream dependency failure before retrying the PR #868 smoke path.",
            },
            {
                "id": "prepare_data",
                "description": "Download the tokenizer and one training shard for a cheap smoke validation.",
                "command": "bash scripts/prepare_parameter_golf_data.sh",
                "cwd": "${REPO_DIR}",
                "log_name": "prepare_data.log",
                "env": {
                    "TRAIN_SHARDS": "1",
                },
                "failure_summary": "Fix the data bootstrap issue before retrying the PR #868 smoke path.",
            },
            {
                "id": "run_smoke",
                "description": "Run the upstream PR #868 train_gpt.py on 1 GPU with the published budgeted two-pass cache settings.",
                "command": "bash scripts/run_upstream_record.sh",
                "cwd": "${REPO_DIR}",
                "log_name": "pr868_smoke.log",
                "env": {
                    "RUN_ID": "pr868_smoke",
                    "RUN_PROFILE": "debug_1gpu_200step",
                    "MODEL_PRESET": "frontier_lean",
                    "TTT_ENABLED": "0",
                    "QAT_MODE": "off",
                    "NGRAM_EVAL_ENABLED": "1",
                    "NGRAM_EVAL_MAX_ORDER": "12",
                    "NGRAM_TWO_PASS_ENABLED": "1",
                    "NGRAM_TWO_PASS_RESCORE_CHUNKS": "72",
                    "NGRAM_BUDGETED_TUNER": "1",
                    "NGRAM_BUDGET_TARGET_SECONDS": "580",
                    "NGRAM_BUDGET_SAFETY_SECONDS": "8",
                    "NPROC_PER_NODE": "1",
                },
                "failure_summary": "Keep the cache smoke run on 1x H100 until it completes cleanly. Do not promote to 8x while operational failures remain.",
            },
        ],
        "success_summary": "PR #868 smoke completed. Review BPB, eval behavior, and legality logs before allowing the full 8x reproduction.",
        "manual_next_spec": str(full_path),
        "manual_next_command": f"Review the smoke report, then run the full spec: python3 scripts/operator_supervisor.py {full_path}",
    }
    full_spec = {
        "schema_version": 1,
        "run_id": "repro_pr868_full",
        "hypothesis": "Reproduce PR #868 on 8x H100 SXM using the published budgeted two-pass n-gram cache settings.",
        "parent_branch": "repro/pr868",
        "track": "cache",
        "compute_tier": "8xH100-SXM",
        "auto_promote": False,
        "promotion_gate": "Full repro must produce a clean terminal result before any more aggressive cache route is allowed.",
        "env": env,
        "phases": [
            {
                "id": "bootstrap_env",
                "description": "Prepare the repo, virtualenv, zstandard, and flash_attn_interface on the 8x pod.",
                "command": "bash scripts/bootstrap_runpod_env.sh",
                "cwd": "${REPO_DIR}",
                "log_name": "bootstrap_env.log",
                "failure_summary": "Fix the bootstrap path before retrying the full PR #868 reproduction.",
            },
            {
                "id": "install_requirements",
                "description": "Install the PR-specific requirements before running the 8x record path.",
                "command": "bash scripts/install_upstream_requirements.sh",
                "cwd": "${REPO_DIR}",
                "log_name": "install_requirements.log",
                "failure_summary": "Fix the upstream dependency failure before retrying the full PR #868 run.",
            },
            {
                "id": "prepare_data",
                "description": "Download the full sp1024 dataset cache before training and eval.",
                "command": "bash scripts/prepare_parameter_golf_data.sh",
                "cwd": "${REPO_DIR}",
                "log_name": "prepare_data.log",
                "failure_summary": "Fix the data bootstrap issue before retrying the full PR #868 run.",
            },
            {
                "id": "run_full_repro",
                "description": "Run the published PR #868 record path on 8 GPUs.",
                "command": "bash scripts/run_upstream_record.sh",
                "cwd": "${REPO_DIR}",
                "log_name": "pr868_full.log",
                "env": {
                    "RUN_ID": "pr868_full",
                    "RUN_PROFILE": "full_8gpu_600s",
                    "MODEL_PRESET": "frontier_lean",
                    "TTT_ENABLED": "0",
                    "QAT_MODE": "off",
                    "NGRAM_EVAL_ENABLED": "1",
                    "NGRAM_EVAL_MAX_ORDER": "12",
                    "NGRAM_TWO_PASS_ENABLED": "1",
                    "NGRAM_TWO_PASS_RESCORE_CHUNKS": "72",
                    "NGRAM_BUDGETED_TUNER": "1",
                    "NGRAM_BUDGET_TARGET_SECONDS": "580",
                    "NGRAM_BUDGET_SAFETY_SECONDS": "8",
                    "NPROC_PER_NODE": "8",
                },
                "failure_summary": "Investigate the exact PR #868 repro failure before trying any higher-upside cache route.",
            },
        ],
        "success_summary": "PR #868 full repro completed. Capture BPB, eval time, and artifact size before any #933 work.",
        "manual_next_command": "Write 09_RESULTS/repro_868.md and decide whether the higher-upside #933 path is justified.",
    }
    atomic_write_json(smoke_path, smoke_spec)
    atomic_write_json(full_path, full_spec)
    return {"smoke": smoke_path, "full": full_path}


def build_pr933_specs(generated_root: Path) -> dict[str, Path]:
    ensure_dirs(generated_root)
    smoke_path = generated_root / "repro_pr933_smoke.json"
    full_path = generated_root / "repro_pr933_full.json"
    env = {
        **common_spec_env(),
        "UPSTREAM_RECORD_DIR": "third_party/upstream_prs/pr933",
        "RUN_ENTRYPOINT": "train_gpt.py",
    }
    smoke_spec = {
        "schema_version": 1,
        "run_id": "repro_pr933_smoke",
        "hypothesis": "Stage a non-autonomous smoke harness for PR #933 while legality remains under active discussion.",
        "parent_branch": "repro/pr933",
        "track": "cache",
        "compute_tier": "1xH100-smoke",
        "auto_promote": False,
        "promotion_gate": "Do not auto-launch this spec. PR #933 requires explicit legality review before any spend.",
        "env": env,
        "phases": [
            {
                "id": "bootstrap_env",
                "description": "Prepare the repo, virtualenv, zstandard, and flash_attn_interface.",
                "command": "bash scripts/bootstrap_runpod_env.sh",
                "cwd": "${REPO_DIR}",
                "log_name": "bootstrap_env.log",
                "failure_summary": "Fix bootstrap before attempting any PR #933 smoke run.",
            },
            {
                "id": "prepare_data",
                "description": "Download one training shard for a cheap future PR #933 smoke validation.",
                "command": "bash scripts/prepare_parameter_golf_data.sh",
                "cwd": "${REPO_DIR}",
                "log_name": "prepare_data.log",
                "env": {
                    "TRAIN_SHARDS": "1",
                },
                "failure_summary": "Fix the data path before attempting any PR #933 smoke run.",
            },
            {
                "id": "run_smoke",
                "description": "Run the upstream PR #933 path on 1 GPU only after explicit legality approval.",
                "command": "bash scripts/run_upstream_record.sh",
                "cwd": "${REPO_DIR}",
                "log_name": "pr933_smoke.log",
                "env": {
                    "RUN_ID": "pr933_smoke",
                    "NPROC_PER_NODE": "1",
                    "MAX_WALLCLOCK_SECONDS": "120",
                },
                "failure_summary": "PR #933 is advisory-only until legality is cleared. Do not auto-promote or auto-retry this path.",
            },
        ],
        "success_summary": "PR #933 smoke spec exists for future manual review only.",
        "manual_next_command": "Manual only: review the legality memo before spending any compute on PR #933.",
    }
    full_spec = {
        "schema_version": 1,
        "run_id": "repro_pr933_full",
        "hypothesis": "Stage the published PR #933 full cache route for manual-only follow-on work.",
        "parent_branch": "repro/pr933",
        "track": "cache",
        "compute_tier": "8xH100-SXM",
        "auto_promote": False,
        "promotion_gate": "Manual only. PR #933 remains disabled for autonomous spend.",
        "env": env,
        "phases": [
            {
                "id": "bootstrap_env",
                "description": "Prepare the repo, virtualenv, zstandard, and flash_attn_interface.",
                "command": "bash scripts/bootstrap_runpod_env.sh",
                "cwd": "${REPO_DIR}",
                "log_name": "bootstrap_env.log",
                "failure_summary": "Fix bootstrap before attempting any PR #933 full run.",
            },
            {
                "id": "prepare_data",
                "description": "Download the full sp1024 dataset cache before the published PR #933 run.",
                "command": "bash scripts/prepare_parameter_golf_data.sh",
                "cwd": "${REPO_DIR}",
                "log_name": "prepare_data.log",
                "failure_summary": "Fix the data path before attempting any PR #933 full run.",
            },
            {
                "id": "run_full_repro",
                "description": "Run the upstream PR #933 path on 8 GPUs only after manual approval.",
                "command": "bash scripts/run_upstream_record.sh",
                "cwd": "${REPO_DIR}",
                "log_name": "pr933_full.log",
                "env": {
                    "RUN_ID": "pr933_full",
                    "NPROC_PER_NODE": "8",
                },
                "failure_summary": "PR #933 remains a manual-only target until legality is explicitly accepted.",
            },
        ],
        "success_summary": "PR #933 full spec exists for future manual review only.",
        "manual_next_command": "Manual only: review the legality memo before spending any compute on PR #933.",
    }
    atomic_write_json(smoke_path, smoke_spec)
    atomic_write_json(full_path, full_spec)
    return {"smoke": smoke_path, "full": full_path}


def generate_specs(control_root: Path) -> dict[str, dict[str, Path]]:
    generated_root = control_root / "generated_specs"
    ensure_dirs(generated_root)
    return {
        "868": build_pr868_specs(generated_root),
        "933": build_pr933_specs(generated_root),
    }


def evaluate_queue(
    policy: dict[str, Any],
    frontier_snapshot: dict[str, Any],
    budget_state: dict[str, Any],
    live_root: Path,
    generated_specs: dict[str, dict[str, Path]],
    supervisor_proc: subprocess.Popen[str] | None,
) -> dict[str, Any]:
    queue_state: dict[str, Any] = {
        "updated_at": utc_now(),
        "blocked": False,
        "blocked_reason": "",
        "active_runs": any_active_live_run(live_root),
        "candidates": frontier_snapshot.get("targets", []),
        "next_spec": None,
        "next_run_id": None,
        "next_target_pr": None,
    }
    if supervisor_proc is not None and supervisor_proc.poll() is None:
        queue_state["blocked"] = True
        queue_state["blocked_reason"] = "supervisor_process_active"
        return queue_state
    if queue_state["active_runs"]:
        queue_state["blocked"] = True
        queue_state["blocked_reason"] = "live_run_active"
        return queue_state
    if budget_state.get("active_pod_count", 0) > 0:
        queue_state["blocked"] = True
        queue_state["blocked_reason"] = "runpod_pod_active"
        return queue_state

    smoke = live_run_snapshot(live_root, "repro_pr868_smoke")
    full = live_run_snapshot(live_root, "repro_pr868_full")
    smoke_terminal = smoke.get("terminal_result", {}).get("status")
    full_terminal = full.get("terminal_result", {}).get("status")
    smoke_supervisor = smoke.get("supervisor_state", {}).get("status")
    full_supervisor = full.get("supervisor_state", {}).get("status")

    if smoke_supervisor in {"launching", "watching"} or full_supervisor in {"launching", "watching"}:
        queue_state["blocked"] = True
        queue_state["blocked_reason"] = "orphaned_supervisor_state_manual_review"
        return queue_state
    if smoke_terminal == "failed":
        queue_state["blocked"] = True
        queue_state["blocked_reason"] = "pr868_smoke_failed_manual_review"
        return queue_state
    if full_terminal == "failed":
        queue_state["blocked"] = True
        queue_state["blocked_reason"] = "pr868_full_failed_manual_review"
        return queue_state
    if smoke_terminal in {"complete", "dry-run-complete"} and full_terminal in {"complete", "dry-run-complete"}:
        queue_state["blocked"] = True
        queue_state["blocked_reason"] = "pr868_full_already_complete"
        return queue_state

    if smoke_terminal not in {"complete", "dry-run-complete"}:
        next_spec = generated_specs["868"]["smoke"]
        next_run_id = "repro_pr868_smoke"
    else:
        next_spec = generated_specs["868"]["full"]
        next_run_id = "repro_pr868_full"

    next_spec_payload = read_json_if_exists(next_spec)
    tier = next_spec_payload.get("compute_tier", "1xH100-smoke")
    reserve_hours = float(policy["reserve_hours_by_tier"].get(tier, 1.0))
    reserve_usd = COST_ESTIMATES.get(tier, 0.0) * reserve_hours
    minimum_balance = float(policy["daily_caps"]["minimum_runpod_balance_reserve_usd"])
    available_balance = float(budget_state["client_balance"])
    reserved_today = float(budget_state["reserved_today_usd"])
    daily_cap = float(policy["daily_caps"]["runpod_usd"])
    if reserved_today + reserve_usd > daily_cap:
        queue_state["blocked"] = True
        queue_state["blocked_reason"] = "daily_cap_would_be_exceeded"
        queue_state["required_reserve_usd"] = round(reserve_usd, 4)
        return queue_state
    if available_balance - reserve_usd < minimum_balance:
        queue_state["blocked"] = True
        queue_state["blocked_reason"] = "minimum_balance_reserve_would_be_breached"
        queue_state["required_reserve_usd"] = round(reserve_usd, 4)
        return queue_state

    queue_state.update(
        {
            "next_spec": str(next_spec),
            "next_run_id": next_run_id,
            "next_target_pr": 868,
            "next_compute_tier": tier,
            "required_reserve_usd": round(reserve_usd, 4),
        }
    )
    return queue_state


def start_dashboard_if_needed(host: str, port: int, live_root: Path, control_root: Path) -> subprocess.Popen[str] | None:
    if port <= 0 or is_port_open(host, port):
        return None
    return subprocess.Popen(
        [
            sys.executable,
            str(repo_root() / "scripts" / "serve_run_control_dashboard.py"),
            "--host",
            host,
            "--port",
            str(port),
            "--live-root",
            str(live_root),
            "--control-plane-root",
            str(control_root),
        ],
        cwd=str(repo_root()),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )


def maybe_launch_next(
    queue_state: dict[str, Any],
    state_root: Path,
    policy: dict[str, Any],
) -> subprocess.Popen[str] | None:
    next_spec = queue_state.get("next_spec")
    if queue_state.get("blocked") or not next_spec:
        return None

    command = [
        sys.executable,
        str(repo_root() / "scripts" / "operator_supervisor.py"),
        next_spec,
        "--max-infra-retries",
        "1",
    ]
    next_compute_tier = queue_state.get("next_compute_tier")
    if next_compute_tier == "1xH100-smoke":
        smoke_gpu = policy.get("smoke_gpu_id")
        if smoke_gpu:
            command.extend(["--gpu-id", smoke_gpu, "--gpu-count", "1"])

    for env_name, arg_name in (
        ("RUN_NOTIFY_WEBHOOK_URL", "--webhook-url"),
        ("TELEGRAM_BOT_TOKEN", "--telegram-bot-token"),
        ("TELEGRAM_CHAT_ID", "--telegram-chat-id"),
    ):
        env_value = os.environ.get(env_name)
        if env_value:
            command.extend([arg_name, env_value])

    proc = subprocess.Popen(
        command,
        cwd=str(repo_root()),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )
    append_jsonl(
        state_root / "launch_events.jsonl",
        {
            "event": "auto_launch_started",
            "timestamp": utc_now(),
            "run_id": queue_state["next_run_id"],
            "target_pr": queue_state["next_target_pr"],
            "spec_path": next_spec,
            "compute_tier": next_compute_tier,
            "reserve_usd": queue_state.get("required_reserve_usd", 0.0),
            "pid": proc.pid,
        },
    )
    return proc


def build_operator_state(
    policy_path: Path,
    state_root: Path,
    budget_state: dict[str, Any],
    frontier_snapshot: dict[str, Any],
    queue_state: dict[str, Any],
    dashboard_proc: subprocess.Popen[str] | None,
    supervisor_proc: subprocess.Popen[str] | None,
) -> dict[str, Any]:
    return {
        "updated_at": utc_now(),
        "policy_path": str(policy_path),
        "state_root": str(state_root),
        "budget_state_path": str(state_root / "budget_state.json"),
        "frontier_snapshot_path": str(state_root / "frontier_snapshot.json"),
        "queue_path": str(state_root / "queue.json"),
        "dashboard_pid": dashboard_proc.pid if dashboard_proc and dashboard_proc.poll() is None else None,
        "supervisor_pid": supervisor_proc.pid if supervisor_proc and supervisor_proc.poll() is None else None,
        "active_target": queue_state.get("next_target_pr"),
        "active_run_id": queue_state.get("next_run_id"),
        "client_balance": budget_state.get("client_balance"),
        "active_pod_count": budget_state.get("active_pod_count"),
        "top_ranked_target": frontier_snapshot.get("targets", [{}])[0].get("pr") if frontier_snapshot.get("targets") else None,
        "queue_blocked": queue_state.get("blocked"),
        "queue_blocked_reason": queue_state.get("blocked_reason"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local guardrailed control-plane daemon for Parameter Golf.")
    parser.add_argument("--policy", default="11_RUN_CONTROL/control_plane/operator_policy.json")
    parser.add_argument("--state-root", default="11_RUN_CONTROL/control_plane/state")
    parser.add_argument("--live-root", default="11_RUN_CONTROL/live")
    parser.add_argument("--dashboard-host", default="127.0.0.1")
    parser.add_argument("--dashboard-port", type=int, default=8787)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-launch", action="store_true")
    parser.add_argument("--no-dashboard", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    root = repo_root()
    policy_path = (root / args.policy).resolve()
    state_root = (root / args.state_root).resolve()
    live_root = (root / args.live_root).resolve()
    control_root = state_root.parent
    events_path = state_root / "events.jsonl"
    ensure_dirs(state_root, live_root, control_root / "advisory", control_root / "generated_specs", control_root / "upstream_prs")

    policy = read_json_if_exists(policy_path)
    if not policy:
        raise SystemExit(f"Policy file missing or invalid: {policy_path}")

    dashboard_proc: subprocess.Popen[str] | None = None
    if not args.no_dashboard and not args.once:
        dashboard_proc = start_dashboard_if_needed(args.dashboard_host, args.dashboard_port, live_root, control_root)

    frontier_due = 0.0
    budget_due = 0.0
    queue_due = 0.0
    frontier_snapshot = read_json_if_exists(state_root / "frontier_snapshot.json")
    budget_state = read_json_if_exists(state_root / "budget_state.json")
    supervisor_proc: subprocess.Popen[str] | None = None
    generated_specs = generate_specs(control_root)

    while True:
        now = time.monotonic()
        if now >= frontier_due or not frontier_snapshot:
            frontier_snapshot = sync_frontier(policy, control_root, state_root, events_path)
            frontier_due = now + float(policy["poll_intervals_seconds"]["frontier"])
            generated_specs = generate_specs(control_root)
        if now >= budget_due or not budget_state:
            budget_state = refresh_budget(policy, state_root, events_path)
            budget_due = now + float(policy["poll_intervals_seconds"]["budget"])
        if now >= queue_due:
            queue_state = evaluate_queue(policy, frontier_snapshot, budget_state, live_root, generated_specs, supervisor_proc)
            atomic_write_json(state_root / "queue.json", queue_state)
            append_jsonl(
                events_path,
                {
                    "event": "queue_evaluated",
                    "timestamp": utc_now(),
                    "blocked": queue_state.get("blocked"),
                    "blocked_reason": queue_state.get("blocked_reason"),
                    "next_run_id": queue_state.get("next_run_id"),
                },
            )
            if not args.no_launch and supervisor_proc is None and queue_state.get("next_spec") and not queue_state.get("blocked"):
                supervisor_proc = maybe_launch_next(queue_state, state_root, policy)
            if supervisor_proc is not None and supervisor_proc.poll() is not None:
                supervisor_proc = None
            operator_state = build_operator_state(
                policy_path,
                state_root,
                budget_state,
                frontier_snapshot,
                queue_state,
                dashboard_proc,
                supervisor_proc,
            )
            atomic_write_json(state_root / "operator_state.json", operator_state)
            queue_due = now + float(policy["poll_intervals_seconds"]["queue"])
        if args.once:
            break
        time.sleep(1.0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
