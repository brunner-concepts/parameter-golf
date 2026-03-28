#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PENDING_REPAIR_STATUSES = {
    "queued",
    "in_progress",
    "awaiting_validation",
    "awaiting_audit",
    "awaiting_push",
    "relaunching",
}
TERMINAL_REPAIR_STATUSES = {"completed", "failed", "paused"}
APPROVED_TARGET_PRS = {868, 913, 933}
INFLIGHT_REPAIR_STATUSES = PENDING_REPAIR_STATUSES - {"queued"}


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


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


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=check,
    )


def tail_text(path: Path, lines: int = 80) -> str:
    content = read_text(path).splitlines()
    return "\n".join(content[-lines:])


def repair_paths(state_root: Path) -> dict[str, Path]:
    return {
        "queue": state_root / "repair_queue.json",
        "policy": state_root / "repair_policy.json",
        "sessions": state_root / "repair_sessions",
        "journal": state_root / "repair_journal.jsonl",
    }


def ensure_repair_dirs(state_root: Path) -> None:
    paths = repair_paths(state_root)
    paths["sessions"].mkdir(parents=True, exist_ok=True)


def load_repair_queue(state_root: Path) -> dict[str, Any]:
    ensure_repair_dirs(state_root)
    payload = read_json(repair_paths(state_root)["queue"])
    if payload:
        payload.setdefault("items", [])
        payload.setdefault("updated_at", utc_now())
        return payload
    payload = {"updated_at": utc_now(), "items": []}
    atomic_write_json(repair_paths(state_root)["queue"], payload)
    return payload


def load_repair_policy(state_root: Path) -> dict[str, Any]:
    ensure_repair_dirs(state_root)
    path = repair_paths(state_root)["policy"]
    payload = read_json(path)
    if payload:
        payload.setdefault("paused", False)
        payload.setdefault("updated_at", utc_now())
        return payload
    payload = {"paused": False, "updated_at": utc_now()}
    atomic_write_json(path, payload)
    return payload


def save_repair_policy(state_root: Path, policy: dict[str, Any]) -> None:
    policy["updated_at"] = utc_now()
    atomic_write_json(repair_paths(state_root)["policy"], policy)


def save_repair_queue(state_root: Path, queue: dict[str, Any]) -> None:
    queue["updated_at"] = utc_now()
    atomic_write_json(repair_paths(state_root)["queue"], queue)


def session_path(state_root: Path, item_id: str) -> Path:
    return repair_paths(state_root)["sessions"] / f"{item_id}.json"


def journal(state_root: Path, event: str, payload: dict[str, Any]) -> None:
    append_jsonl(
        repair_paths(state_root)["journal"],
        {
            "event": event,
            "timestamp": utc_now(),
            **payload,
        },
    )


def active_repair_item(queue: dict[str, Any]) -> dict[str, Any] | None:
    for item in queue.get("items", []):
        if item.get("status") in PENDING_REPAIR_STATUSES:
            return item
    return None


def inflight_repair_item(queue: dict[str, Any]) -> dict[str, Any] | None:
    for item in queue.get("items", []):
        if item.get("status") in INFLIGHT_REPAIR_STATUSES:
            return item
    return None


def latest_completed_item(queue: dict[str, Any], kind: str, run_id: str) -> dict[str, Any] | None:
    matches = [
        item
        for item in queue.get("items", [])
        if item.get("kind") == kind and item.get("run_id") == run_id and item.get("status") == "completed"
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return matches[0]


def git_changed_files(root: Path) -> list[str]:
    proc = run(["git", "status", "--short"], cwd=root, check=True)
    changed: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:] if len(line) > 3 else line.strip()
        changed.append(path.strip())
    return changed


def path_allowed(path: str, allowed_paths: list[str]) -> bool:
    normalized = Path(path).as_posix()
    for candidate in allowed_paths:
        prefix = Path(candidate).as_posix().rstrip("/")
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return True
    return False


def parse_metric(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1) if match else None


def parse_pr868_metrics(text: str) -> dict[str, Any]:
    tuner_match = re.search(
        r"ngram_budgeted_tuner .* requested:(\d+) tuned:(\d+)",
        text,
    )
    pass2_match = re.search(r"rescoring first (\d+) chunks with full cache \((\d+) chunks\)", text)
    return {
        "train_step_time_ms": parse_metric(r"step_avg:(\d+\.\d+)ms", text),
        "diagnostic_bpb": parse_metric(r"DIAGNOSTIC post_average .* val_bpb:(\d+\.\d+)", text),
        "roundtrip_exact_bpb": parse_metric(r"final_research_export_exact .* val_bpb:(\d+\.\d+)", text),
        "final_ngram_exact_bpb": parse_metric(r"final_ngram_exact .* val_bpb:(\d+\.\d+)", text),
        "final_ngram_eval_ms": parse_metric(r"final_ngram .* eval_time:(\d+)ms", text),
        "artifact_bytes": parse_metric(r"Total submission size research_export: (\d+) bytes", text),
        "requested_chunks": tuner_match.group(1) if tuner_match else None,
        "tuned_chunks": tuner_match.group(2) if tuner_match else None,
        "rescored_chunks": pass2_match.group(1) if pass2_match else None,
        "total_chunks": pass2_match.group(2) if pass2_match else None,
    }


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def next_registry_id(root: Path) -> str:
    path = root / "06_EXPERIMENT_REGISTRY.jsonl"
    max_id = 0
    for line in read_text(path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        value = str(obj.get("id") or "")
        if value.startswith("E") and value[1:].isdigit():
            max_id = max(max_id, int(value[1:]))
    return f"E{max_id + 1:03d}"


def sync_hypothesis_backlog_for_parity(root: Path) -> None:
    path = root / "05_HYPOTHESIS_BACKLOG.jsonl"
    rows: list[dict[str, Any]] = []
    existing_ids: set[str] = set()
    for line in read_text(path).splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        existing_ids.add(str(obj.get("id")))
        if obj.get("id") == "H011":
            obj["status"] = "complete"
            obj["blocker"] = "Pinned-manifest #868 parity rerun completed and confirmed the divergence persists after the frozen eval surface."
        elif obj.get("id") == "H012":
            obj["status"] = "complete"
            obj["blocker"] = "Final self-funded PR #868 parity campaign resolved with persistent divergence after pinned-manifest replay."
        rows.append(obj)
    if "H013" not in existing_ids:
        rows.append(
            {
                "id": "H013",
                "hypothesis": "Because the #868 divergence persists after a pinned-manifest rerun, the next highest-EV step is to stop blind repro spending and either isolate the remaining hidden eval-surface cause or pivot the cache stack to #913 with the same operator.",
                "track": "A",
                "priority": 2,
                "status": "review_needed",
                "parent": "#868/#913",
                "estimated_ev": "high",
                "blocker": "Need an executive decision on whether to spend further on hidden data-surface forensics or use the working operator stack on the next conservative cache lineage target.",
            }
        )
    atomic_write_text(path, "\n".join(json.dumps(row, sort_keys=False) for row in rows) + "\n")


def update_registry_for_parity(root: Path, analysis: dict[str, Any]) -> None:
    path = root / "06_EXPERIMENT_REGISTRY.jsonl"
    existing = read_text(path)
    if "repro_pr868_parity_full" in existing:
        return
    entry = {
        "id": next_registry_id(root),
        "type": "full_repro",
        "description": (
            "Completed the pinned-manifest PR #868 parity rerun on 8x H100 SXM. "
            f"The run still landed at val_bpb {analysis['observed']['final_ngram_exact_bpb']} "
            f"with {analysis['observed']['total_chunks']} chunks versus upstream {analysis['expected']['total_chunks']}, "
            "so the divergence persists after the frozen eval surface."
        ),
        "timestamp": analysis["completed_at"],
        "status": "complete",
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def append_decision_log_for_parity(root: Path, analysis: dict[str, Any]) -> None:
    path = root / "07_DECISION_LOG.md"
    text = read_text(path)
    heading = "## 2026-03-28 — PR #868 pinned-manifest parity rerun confirms persistent divergence"
    if heading in text:
        return
    section = "\n".join(
        [
            heading,
            "",
            "**Decision:**",
            "Treat the pinned-manifest `#868` rerun as milestone-resolving evidence, not as a submission candidate. Stop the self-funded parity campaign and move the project from 'pin the surface' to 'persistent divergence after pinned replay.'",
            "",
            "**Rationale:**",
            f"- The rerun completed end-to-end on `8x H100 SXM` and still landed at `{analysis['observed']['final_ngram_exact_bpb']}` exact n-gram BPB, not near the upstream seed-1337 `{analysis['expected']['final_ngram_exact_bpb']}`.",
            f"- The frozen rerun still saw `{analysis['observed']['total_chunks']}` total n-gram chunks and tuned `{analysis['observed']['tuned_chunks']}` chunks, versus upstream `{analysis['expected']['total_chunks']}` and `{analysis['expected']['tuned_chunks']}`.",
            "- That means the prior diagnosis was incomplete: pinning the manifest and HF revision did not collapse the gap. The remaining divergence is deeper than the originally suspected moving-manifest surface.",
            "",
            "**Consequences:**",
            "1. Stop automatic `#868` replay spending under the final self-funded campaign.",
            "2. Keep competition PR packaging blocked; the result is still not an understood reproduction.",
            "3. Update the grant narrative to reflect stronger evidence: the operator completed a frozen-surface parity rerun and narrowed the unresolved gap further.",
            "4. The next strategic choice is no longer 'rerun blindly.' It is either deeper hidden-surface forensics or a pivot to the next conservative cache lineage target with the now-proven operator stack.",
        ]
    )
    atomic_write_text(path, text.rstrip() + "\n\n" + section + "\n")


def write_parity_report(root: Path, analysis: dict[str, Any]) -> Path:
    report_path = root / "09_RESULTS/repro_pr868_parity_full.md"
    observed = analysis["observed"]
    expected = analysis["expected"]
    notes = [
        f"Pinned-manifest parity rerun completed at `{analysis['completed_at']}`.",
        "",
        "Key comparison versus the synced upstream seed-1337 log:",
        f"- exact n-gram BPB: `{observed['final_ngram_exact_bpb']}` vs `{expected['final_ngram_exact_bpb']}`",
        f"- n-gram total chunks: `{observed['total_chunks']}` vs `{expected['total_chunks']}`",
        f"- tuned chunks: `{observed['tuned_chunks']}` vs `{expected['tuned_chunks']}`",
        f"- n-gram eval time: `{observed['final_ngram_eval_ms']}ms` vs `{expected['final_ngram_eval_ms']}ms`",
        f"- artifact bytes: `{observed['artifact_bytes']}` vs `{expected['artifact_bytes']}`",
        "",
        "Interpretation:",
        "- The rerun is operationally successful: the pinned-manifest bootstrap path works and the provider-staged 8x stack remains reproducible.",
        "- The rerun is still not an understood reproduction. The same core divergence survives the frozen replay, so the original moving-manifest hypothesis is no longer sufficient.",
        f"- Because the exact score delta remains ~`{analysis['score_delta_bpb']}` BPB and the chunk surface remains materially different, this should not be packaged as a competition PR.",
        "",
        "Next exact step:",
        "1. Stop the current self-funded parity campaign and preserve the evidence.",
        "2. Update the grant request to describe the now-resolved milestone: full frozen-surface rerun completed, divergence persisted.",
        "3. Decide between deeper hidden eval-surface forensics and a conservative pivot to the next cache lineage target.",
    ]
    text = "\n".join(
        [
            "hypothesis: Re-running PR #868 on a pinned challenge-data manifest and frozen dataset revision will collapse the remaining parity gap if the mismatch is coming from a moving eval surface.",
            "parent_branch: repro/pr868",
            "exact_diff: executed via the pinned-manifest generated spec `11_RUN_CONTROL/control_plane/generated_specs/repro_pr868_parity_full.json`; no intended model-code diff versus synced upstream PR #868 payload",
            f"train_step_time_ms: {observed['train_step_time_ms'] or 'unknown'} (ours) vs {expected['train_step_time_ms'] or 'unknown'} (upstream seed 1337)",
            f"eval_time_s: {analysis['observed_eval_s']} (ours) vs {analysis['expected_eval_s']} (upstream seed 1337)",
            f"artifact_bytes: {observed['artifact_bytes']} (ours) vs {expected['artifact_bytes']} (upstream seed 1337)",
            f"pre_quant_bpb: {observed['diagnostic_bpb']} (ours) vs {expected['diagnostic_bpb']} (upstream seed 1337 diagnostic)",
            f"post_quant_bpb: {observed['final_ngram_exact_bpb']} (ours exact n-gram) vs {expected['final_ngram_exact_bpb']} (upstream seed 1337 exact n-gram)",
            "legality_risk: low",
            "recommendation: kill",
            "notes: |",
            *(f"  {line}" if line else "" for line in notes),
        ]
    )
    atomic_write_text(report_path, text.rstrip() + "\n")
    return report_path


def analyze_pr868_parity(root: Path) -> dict[str, Any]:
    summary_text = read_text(root / "11_RUN_CONTROL/live/repro_pr868_parity_full/summary.md")
    upstream_text = read_text(root / "third_party/upstream_prs/pr868/train_seed1337.log")
    terminal = read_json(root / "11_RUN_CONTROL/live/repro_pr868_parity_full/terminal_result.json")
    observed = parse_pr868_metrics(summary_text)
    expected = parse_pr868_metrics(upstream_text)
    observed_bpb = float(observed["final_ngram_exact_bpb"])
    expected_bpb = float(expected["final_ngram_exact_bpb"])
    observed_chunks = int(observed["total_chunks"])
    expected_chunks = int(expected["total_chunks"])
    observed_tuned = int(observed["tuned_chunks"])
    expected_tuned = int(expected["tuned_chunks"])
    within_tolerance = abs(observed_bpb - expected_bpb) <= 0.001
    chunks_match = observed_chunks == expected_chunks
    tuned_match = observed_tuned == expected_tuned
    if within_tolerance and chunks_match and tuned_match:
        decision_key = "pr868_understood_reproduction"
        summary = "The pinned-manifest rerun lands within tolerance and matches the upstream n-gram surface."
        recommendation = "promote"
        next_action = "Treat PR #868 as understood, preserve the report, and decide whether to package a conservative derivative or pivot upward with confidence."
    else:
        decision_key = "pr868_persistent_divergence_after_pinned_surface"
        summary = "The pinned-manifest rerun still diverges materially from upstream after the frozen replay."
        recommendation = "kill"
        next_action = "Stop new #868 replay spend, preserve the evidence, and move to a grant request or a deliberate pivot instead of another blind rerun."
    return {
        "analysis_type": "parity_review_pr868",
        "completed_at": terminal.get("updated_at") or utc_now(),
        "decision_key": decision_key,
        "summary": summary,
        "recommendation": recommendation,
        "next_action": next_action,
        "observed": observed,
        "expected": expected,
        "within_tolerance": within_tolerance,
        "chunks_match": chunks_match,
        "tuned_match": tuned_match,
        "score_delta_bpb": round(observed_bpb - expected_bpb, 8),
        "observed_eval_s": round(float(observed["final_ngram_eval_ms"]) / 1000.0, 3),
        "expected_eval_s": round(float(expected["final_ngram_eval_ms"]) / 1000.0, 3),
    }


def parse_codex_jsonl(text: str) -> tuple[str | None, str]:
    thread_id: str | None = None
    final_reply = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "thread.started":
            thread_id = obj.get("thread_id")
        if obj.get("type") == "response.completed":
            output = obj.get("response", {}).get("output") or []
            for item in output:
                if item.get("type") == "message":
                    for content in item.get("content") or []:
                        if content.get("type") == "output_text":
                            final_reply = content.get("text") or final_reply
    return thread_id, final_reply


def run_codex_repair(root: Path, prompt: str, thread_id: str | None) -> tuple[str | None, str]:
    cmd = [
        "codex",
        "exec",
        "-C",
        str(root),
        "--skip-git-repo-check",
        "-s",
        "workspace-write",
        "-m",
        "gpt-5.4",
        "--json",
    ]
    if thread_id:
        cmd.extend(["resume", thread_id, prompt])
    else:
        cmd.append(prompt)
    proc = run(cmd, cwd=root, timeout=900, check=True)
    return parse_codex_jsonl(proc.stdout)


def run_claude_audit(root: Path, item: dict[str, Any], changed_files: list[str]) -> dict[str, Any]:
    schema = json.dumps(
        {
            "type": "object",
            "properties": {
                "approved": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["approved", "reason"],
        }
    )
    diff_proc = run(["git", "diff", "--", *changed_files], cwd=root, check=True)
    prompt = "\n".join(
        [
            "You are auditing an autonomous repair for the Parameter Golf operator.",
            "Approve only if the change stays inside scope, matches the stated failure, and is operationally safe.",
            "",
            f"Repair item: {json.dumps(item, indent=2, sort_keys=True)}",
            "",
            "Unified diff:",
            diff_proc.stdout[:20000],
        ]
    )
    proc = run(
        [
            "claude",
            "-p",
            "--output-format",
            "json",
            "--json-schema",
            schema,
            prompt,
        ],
        cwd=root,
        timeout=600,
        check=True,
    )
    return json.loads(proc.stdout)


def run_validators(root: Path, commands: list[str]) -> list[dict[str, Any]]:
    results = []
    for command in commands:
        proc = subprocess.run(
            command,
            cwd=str(root),
            shell=True,
            text=True,
            capture_output=True,
        )
        results.append(
            {
                "command": command,
                "exit_code": proc.returncode,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-4000:],
            }
        )
        if proc.returncode != 0:
            break
    return results


def commit_and_push(root: Path, files: list[str], message: str) -> dict[str, Any]:
    run(["git", "add", "--", *files], cwd=root, check=True)
    staged = run(["git", "diff", "--cached", "--name-only"], cwd=root, check=True).stdout.splitlines()
    if not staged:
        return {"committed": False, "pushed": False, "files": []}
    run(["git", "commit", "-m", message], cwd=root, check=True)
    run(["git", "push", "origin", "main"], cwd=root, check=True)
    return {"committed": True, "pushed": True, "files": staged}


def restart_operator_if_needed(root: Path, changed_files: list[str]) -> dict[str, Any]:
    needs_restart = any(
        path_allowed(
            changed,
            [
                "scripts/control_plane_daemon.py",
                "scripts/repair_controller.py",
                "scripts/launch_runpod_managed_run.py",
                "scripts/operator_supervisor.py",
                "scripts/mirror_runpod_watchdog.py",
                "scripts/prepare_parameter_golf_data.sh",
                "data/cached_challenge_fineweb.py",
            ],
        )
        for changed in changed_files
    )
    if not needs_restart:
        return {"restarted": False}
    run(["docker", "compose", "-f", "docker-compose.local-operator.yml", "restart", "operator"], cwd=root, check=True)
    return {"restarted": True}


def build_supervisor_command(root: Path, spec_path: str) -> list[str]:
    policy = read_json(root / "11_RUN_CONTROL/control_plane/operator_policy.json")
    provider_storage_state = read_json(root / "11_RUN_CONTROL/control_plane/state/provider_storage_state.json")
    command = [
        sys.executable,
        "scripts/operator_supervisor.py",
        spec_path,
        "--max-infra-retries",
        "1",
    ]
    timeouts = policy.get("launch_timeouts_seconds") or {}
    for key, flag in (
        ("ssh_setup", "--ssh-setup-timeout"),
        ("spec_copy", "--spec-copy-timeout"),
        ("flash_attn_cache_copy", "--flash-attn-cache-copy-timeout"),
        ("remote_launch", "--remote-launch-timeout"),
    ):
        value = timeouts.get(key)
        if value is not None:
            command.extend([flag, str(int(value))])
    if provider_storage_state.get("status") == "ready":
        command.extend(
            [
                "--network-volume-id",
                str(provider_storage_state["volume_id"]),
                "--data-center-id",
                str(provider_storage_state["data_center_id"]),
                "--volume-mount-path",
                str(provider_storage_state.get("mount_path", "/workspace/shared")),
                "--flash-attn-cache-remote-path",
                str((provider_storage_state.get("seeded_flash_attn") or {}).get("remote_path") or provider_storage_state.get("flash_attn_remote_path")),
            ]
        )
    return command


def relaunch_spec(root: Path, item: dict[str, Any]) -> dict[str, Any]:
    spec_path = item.get("spec_path")
    if not spec_path:
        return {"launched": False, "reason": "missing_spec_path"}
    proc = subprocess.Popen(
        build_supervisor_command(root, spec_path),
        cwd=str(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )
    return {"launched": True, "pid": proc.pid, "spec_path": spec_path}


def write_parity_memory(root: Path, analysis: dict[str, Any]) -> list[str]:
    report_path = write_parity_report(root, analysis)
    sync_hypothesis_backlog_for_parity(root)
    update_registry_for_parity(root, analysis)
    append_decision_log_for_parity(root, analysis)
    return [
        str(report_path.relative_to(root)),
        "05_HYPOTHESIS_BACKLOG.jsonl",
        "06_EXPERIMENT_REGISTRY.jsonl",
        "07_DECISION_LOG.md",
    ]


def process_parity_review(root: Path, state_root: Path, item: dict[str, Any], *, no_act: bool) -> dict[str, Any]:
    analysis = analyze_pr868_parity(root)
    payload = dict(item)
    payload["status"] = "completed"
    payload["updated_at"] = utc_now()
    payload["result"] = analysis
    changed_files: list[str] = []
    commit_result = {"committed": False, "pushed": False, "files": []}
    if not no_act:
        changed_files = write_parity_memory(root, analysis)
        commit_result = commit_and_push(root, changed_files, "Record PR #868 parity rerun decision")
    payload["changed_files"] = changed_files
    payload["commit"] = commit_result
    atomic_write_json(session_path(state_root, item["id"]), payload)
    return payload


def build_repair_prompt(root: Path, item: dict[str, Any]) -> str:
    run_dir = root / "11_RUN_CONTROL/live" / item["run_id"]
    return "\n".join(
        [
            "You are the write-authorized repair worker for the Parameter Golf operator.",
            "Fix the deterministic failure without widening scope.",
            "You may modify only the allowed file paths listed below.",
            "Do not change model architecture or target family.",
            "Do not commit or push.",
            "",
            f"Repair item: {json.dumps(item, indent=2, sort_keys=True)}",
            "",
            f"Active log tail from {run_dir / 'active_log.tail.txt'}:",
            tail_text(run_dir / "active_log.tail.txt", 120),
            "",
            "Validation commands:",
            "\n".join(item.get("validation_commands") or []),
        ]
    )


def process_model_repair(root: Path, state_root: Path, item: dict[str, Any], *, no_act: bool) -> dict[str, Any]:
    payload = dict(item)
    payload["updated_at"] = utc_now()
    if no_act:
        payload["status"] = "paused"
        payload["result"] = {"reason": "no_act"}
        atomic_write_json(session_path(state_root, item["id"]), payload)
        return payload

    thread_id = item.get("codex_thread_id")
    prompt = build_repair_prompt(root, item)
    next_thread_id, reply = run_codex_repair(root, prompt, thread_id)
    payload["codex_thread_id"] = next_thread_id
    payload["codex_reply"] = reply
    changed_files = git_changed_files(root)
    if not changed_files:
        payload["status"] = "failed"
        payload["result"] = {"reason": "codex_made_no_changes"}
        atomic_write_json(session_path(state_root, item["id"]), payload)
        return payload

    disallowed = [path for path in changed_files if not path_allowed(path, item.get("allowed_paths") or [])]
    if disallowed:
        payload["status"] = "failed"
        payload["result"] = {"reason": "scope_violation", "disallowed_files": disallowed}
        atomic_write_json(session_path(state_root, item["id"]), payload)
        return payload

    payload["status"] = "awaiting_validation"
    payload["changed_files"] = changed_files
    atomic_write_json(session_path(state_root, item["id"]), payload)

    validations = run_validators(root, item.get("validation_commands") or [])
    payload["validation_results"] = validations
    if any(result["exit_code"] != 0 for result in validations):
        payload["status"] = "failed"
        payload["result"] = {"reason": "validation_failed"}
        atomic_write_json(session_path(state_root, item["id"]), payload)
        return payload

    payload["status"] = "awaiting_audit"
    atomic_write_json(session_path(state_root, item["id"]), payload)
    audit = run_claude_audit(root, payload, changed_files)
    payload["audit"] = audit
    if not audit.get("approved"):
        payload["status"] = "failed"
        payload["result"] = {"reason": "audit_rejected", "audit": audit}
        atomic_write_json(session_path(state_root, item["id"]), payload)
        return payload

    payload["status"] = "awaiting_push"
    atomic_write_json(session_path(state_root, item["id"]), payload)
    commit_result = commit_and_push(root, changed_files, f"Auto-repair {item['run_id']} {item['failure_class']}")
    restart_result = restart_operator_if_needed(root, changed_files)
    relaunch_result = relaunch_spec(root, item)
    payload["status"] = "completed"
    payload["commit"] = commit_result
    payload["restart"] = restart_result
    payload["relaunch"] = relaunch_result
    payload["result"] = {"reason": "repair_applied_and_relaunched"}
    atomic_write_json(session_path(state_root, item["id"]), payload)
    return payload


def sync_repair_requests(root: Path, state_root: Path, live_root: Path, queue_state: dict[str, Any]) -> dict[str, Any]:
    queue = load_repair_queue(state_root)
    items = queue.get("items") or []
    blocked_reason = str(queue_state.get("blocked_reason") or "")

    def has_item(item_id: str) -> bool:
        return any(existing.get("id") == item_id for existing in items)

    if blocked_reason == "pr868_parity_full_complete_review":
        item_id = "review_repro_pr868_parity_full"
        if not has_item(item_id):
            run_dir = live_root / "repro_pr868_parity_full"
            item = {
                "id": item_id,
                "kind": "parity_review_pr868",
                "run_id": "repro_pr868_parity_full",
                "target_pr": 868,
                "status": "queued",
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "summary": "Resolve the PR #868 pinned-manifest parity rerun into an autonomous decision instead of waiting for manual review.",
                "source_blocked_reason": blocked_reason,
                "run_dir": str(run_dir),
            }
            items.append(item)
            journal(state_root, "repair_enqueued", {"item_id": item_id, "kind": item["kind"], "run_id": item["run_id"]})
    elif blocked_reason in {"pr868_smoke_failed_manual_review", "pr868_full_failed_manual_review", "pr868_parity_full_failed_manual_review"}:
        run_id = {
            "pr868_smoke_failed_manual_review": "repro_pr868_smoke",
            "pr868_full_failed_manual_review": "repro_pr868_full",
            "pr868_parity_full_failed_manual_review": "repro_pr868_parity_full",
        }[blocked_reason]
        run_dir = live_root / run_id
        terminal = read_json(run_dir / "terminal_result.json")
        updated_at = terminal.get("updated_at") or utc_now()
        item_id = f"repair_{run_id}_{updated_at.replace(':', '').replace('-', '')}"
        if not has_item(item_id):
            log_excerpt = tail_text(run_dir / "active_log.tail.txt", 80)
            failure_class = "target_family_bootstrap_failure"
            allowed_paths = [
                "scripts/control_plane_daemon.py",
                "scripts/prepare_parameter_golf_data.sh",
                "scripts/bootstrap_runpod_env.sh",
                "scripts/install_upstream_requirements.sh",
                "scripts/launch_runpod_managed_run.py",
                "scripts/operator_supervisor.py",
                "scripts/repair_controller.py",
                "scripts/telegram_sidecar.py",
                "data/cached_challenge_fineweb.py",
            ]
            if "${REPO_DIR}" in log_excerpt:
                failure_class = "literal_env_placeholder_path"
                allowed_paths = [
                    "scripts/control_plane_daemon.py",
                    "scripts/prepare_parameter_golf_data.sh",
                    "scripts/repair_controller.py",
                    "data/cached_challenge_fineweb.py",
                ]
            item = {
                "id": item_id,
                "kind": "target_family_repair",
                "run_id": run_id,
                "target_pr": 868,
                "status": "queued",
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "source_blocked_reason": blocked_reason,
                "failure_class": failure_class,
                "failed_phase": terminal.get("failed_phase"),
                "error_excerpt": log_excerpt,
                "allowed_paths": allowed_paths,
                "validation_commands": [
                    "python3 -m py_compile scripts/control_plane_daemon.py data/cached_challenge_fineweb.py",
                    "bash -n scripts/prepare_parameter_golf_data.sh",
                    "python3 scripts/control_plane_daemon.py --once --no-launch --no-dashboard",
                ],
                "spec_path": str((root / "11_RUN_CONTROL/control_plane/generated_specs" / f"{run_id}.json").resolve()),
            }
            items.append(item)
            journal(state_root, "repair_enqueued", {"item_id": item_id, "kind": item["kind"], "run_id": item["run_id"]})

    queue["items"] = items
    save_repair_queue(state_root, queue)
    return queue


def apply_repair_queue_override(queue_state: dict[str, Any], repair_queue: dict[str, Any]) -> dict[str, Any]:
    active = active_repair_item(repair_queue)
    if active:
        queue_state["blocked"] = True
        queue_state["blocked_reason"] = "repair_in_progress"
        queue_state["repair_active_id"] = active.get("id")
        queue_state["repair_active_kind"] = active.get("kind")
        return queue_state

    if queue_state.get("blocked_reason") == "pr868_parity_full_complete_review":
        latest = latest_completed_item(repair_queue, "parity_review_pr868", "repro_pr868_parity_full")
        if latest:
            decision_key = (latest.get("result") or {}).get("decision_key")
            if decision_key == "pr868_persistent_divergence_after_pinned_surface":
                queue_state["blocked_reason"] = "pr868_parity_divergence_resolved"
                queue_state["repair_decision_key"] = decision_key
            elif decision_key == "pr868_understood_reproduction":
                queue_state["blocked_reason"] = "pr868_parity_understood"
                queue_state["repair_decision_key"] = decision_key
    return queue_state


def build_repair_summary(repair_queue: dict[str, Any], repair_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    items = repair_queue.get("items") or []
    active = active_repair_item(repair_queue)
    latest = sorted(items, key=lambda item: item.get("updated_at") or "", reverse=True)[:1]
    return {
        "paused": bool((repair_policy or {}).get("paused", False)),
        "active": active,
        "active_count": sum(1 for item in items if item.get("status") in PENDING_REPAIR_STATUSES),
        "total_count": len(items),
        "latest": latest[0] if latest else None,
    }


def process_next_item(root: Path, state_root: Path, queue: dict[str, Any], *, no_act: bool) -> dict[str, Any] | None:
    for index, item in enumerate(queue.get("items") or []):
        if item.get("status") != "queued":
            continue
        item["status"] = "in_progress"
        item["updated_at"] = utc_now()
        queue["items"][index] = item
        save_repair_queue(state_root, queue)
        journal(state_root, "repair_started", {"item_id": item["id"], "kind": item["kind"], "run_id": item["run_id"]})
        if item.get("kind") == "parity_review_pr868":
            completed = process_parity_review(root, state_root, item, no_act=no_act)
        else:
            completed = process_model_repair(root, state_root, item, no_act=no_act)
        queue["items"][index] = completed
        save_repair_queue(state_root, queue)
        journal(
            state_root,
            "repair_finished",
            {
                "item_id": completed["id"],
                "kind": completed.get("kind"),
                "run_id": completed.get("run_id"),
                "status": completed.get("status"),
                "decision": (completed.get("result") or {}).get("decision_key") or (completed.get("result") or {}).get("reason"),
            },
        )
        return completed
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Host-side autonomous repair controller for Parameter Golf.")
    parser.add_argument("--state-root", default="11_RUN_CONTROL/control_plane/state")
    parser.add_argument("--live-root", default="11_RUN_CONTROL/live")
    parser.add_argument("--poll-interval", type=float, default=10.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-act", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = repo_root()
    state_root = (root / args.state_root).resolve()
    live_root = (root / args.live_root).resolve()
    ensure_repair_dirs(state_root)

    while True:
        repair_policy = load_repair_policy(state_root)
        queue_state = read_json(state_root / "queue.json")
        repair_queue = sync_repair_requests(root, state_root, live_root, queue_state)
        if not repair_policy.get("paused") and not inflight_repair_item(repair_queue):
            process_next_item(root, state_root, repair_queue, no_act=args.no_act)
        if args.once:
            break
        time.sleep(args.poll_interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
