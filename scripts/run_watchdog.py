#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread
from typing import Any

SCHEMA_VERSION = 1
PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class WatchdogError(RuntimeError):
    pass


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


def shell_join(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def expand_value(value: str, context: dict[str, str]) -> str:
    expanded = os.path.expanduser(value)

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return context.get(key, match.group(0))

    return PLACEHOLDER_RE.sub(replace, expanded)


def expand_mapping(mapping: dict[str, Any] | None, context: dict[str, str]) -> dict[str, str]:
    if not mapping:
        return {}
    resolved: dict[str, str] = {}
    available = {**context}
    for key, value in mapping.items():
        if value is None:
            continue
        resolved_value = expand_value(str(value), {**available, **resolved})
        resolved[key] = resolved_value
    return resolved


def load_spec(spec_path: Path) -> dict[str, Any]:
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WatchdogError(f"Spec file not found: {spec_path}") from exc
    except json.JSONDecodeError as exc:
        raise WatchdogError(f"Invalid JSON in {spec_path}: {exc}") from exc

    if spec.get("schema_version") != SCHEMA_VERSION:
        raise WatchdogError(
            f"{spec_path} has schema_version={spec.get('schema_version')!r}; expected {SCHEMA_VERSION}"
        )

    required = ["run_id", "hypothesis", "parent_branch", "track", "compute_tier", "phases"]
    missing = [key for key in required if key not in spec]
    if missing:
        raise WatchdogError(f"{spec_path} is missing required keys: {', '.join(missing)}")

    if spec.get("auto_promote", False):
        raise WatchdogError(f"{spec_path} sets auto_promote=true. Auto-promotion is forbidden.")

    phases = spec.get("phases")
    if not isinstance(phases, list) or not phases:
        raise WatchdogError(f"{spec_path} must contain a non-empty phases array.")

    phase_ids: set[str] = set()
    for index, phase in enumerate(phases, start=1):
        if not isinstance(phase, dict):
            raise WatchdogError(f"{spec_path} phase #{index} is not an object.")
        for key in ("id", "description", "command"):
            if key not in phase:
                raise WatchdogError(f"{spec_path} phase #{index} is missing required key: {key}")
        phase_id = str(phase["id"])
        if phase_id in phase_ids:
            raise WatchdogError(f"{spec_path} contains duplicate phase id: {phase_id}")
        phase_ids.add(phase_id)

    return spec


@dataclass
class Paths:
    state_dir: Path
    runs_dir: Path
    current_state: Path
    heartbeat: Path
    status_txt: Path
    next_action: Path
    terminal_result: Path
    lock: Path


def build_paths(state_dir: Path) -> Paths:
    return Paths(
        state_dir=state_dir,
        runs_dir=state_dir / "runs",
        current_state=state_dir / "current_state.json",
        heartbeat=state_dir / "heartbeat.json",
        status_txt=state_dir / "status.txt",
        next_action=state_dir / "next_action.txt",
        terminal_result=state_dir / "terminal_result.json",
        lock=state_dir / "active_run.lock",
    )


def ensure_base_state(paths: Paths) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.runs_dir.mkdir(parents=True, exist_ok=True)
    if not paths.current_state.exists():
        atomic_write_json(
            paths.current_state,
            {
                "run_id": None,
                "status": "idle",
                "updated_at": utc_now(),
                "message": "No run has been started yet.",
            },
        )
    if not paths.heartbeat.exists():
        atomic_write_json(
            paths.heartbeat,
            {
                "run_id": None,
                "status": "idle",
                "updated_at": utc_now(),
                "message": "No heartbeat available yet.",
            },
        )
    if not paths.status_txt.exists():
        atomic_write_text(paths.status_txt, "status: idle\nrun_id: none\n")
    if not paths.next_action.exists():
        atomic_write_text(
            paths.next_action,
            "No active run.\n\nRecommended command:\npython3 scripts/run_watchdog.py run run_specs/repro_pr414_smoke.json\n",
        )
    if not paths.terminal_result.exists():
        atomic_write_json(
            paths.terminal_result,
            {
                "run_id": None,
                "status": "idle",
                "updated_at": utc_now(),
                "message": "No terminal result recorded yet.",
            },
        )


def pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def acquire_lock(paths: Paths, run_id: str) -> None:
    if paths.lock.exists():
        try:
            lock_data = read_json(paths.lock)
        except Exception:
            lock_data = {}
        pid = lock_data.get("pid")
        if isinstance(pid, int) and pid_is_alive(pid):
            raise WatchdogError(
                f"Another watchdog process is active for run {lock_data.get('run_id')} (pid {pid})."
            )
        paths.lock.unlink(missing_ok=True)

    lock_payload = {
        "pid": os.getpid(),
        "run_id": run_id,
        "started_at": utc_now(),
    }
    atomic_write_json(paths.lock, lock_payload)


def release_lock(paths: Paths) -> None:
    if not paths.lock.exists():
        return
    try:
        lock_data = read_json(paths.lock)
    except Exception:
        paths.lock.unlink(missing_ok=True)
        return
    if lock_data.get("pid") == os.getpid():
        paths.lock.unlink(missing_ok=True)


class OutputPump(Thread):
    def __init__(self, stream: Any, destination: Path, tail_buffer: deque[str]) -> None:
        super().__init__(daemon=True)
        self.stream = stream
        self.destination = destination
        self.tail_buffer = tail_buffer
        self._lock = Lock()

    def run(self) -> None:
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        with self.destination.open("a", encoding="utf-8") as handle:
            if self.stream is None:
                return
            for line in self.stream:
                handle.write(line)
                handle.flush()
                with self._lock:
                    self.tail_buffer.append(line.rstrip("\n"))


def render_status_text(state: dict[str, Any], heartbeat: dict[str, Any]) -> str:
    lines = [
        f"status: {state.get('status', 'unknown')}",
        f"run_id: {state.get('run_id') or 'none'}",
        f"phase: {state.get('phase_id') or 'none'}",
        f"updated_at: {state.get('updated_at')}",
    ]
    if state.get("run_dir"):
        lines.append(f"run_dir: {state['run_dir']}")
    if state.get("active_log"):
        lines.append(f"active_log: {state['active_log']}")
    if heartbeat.get("last_output"):
        lines.append("last_output:")
        lines.extend(f"  {line}" for line in heartbeat["last_output"])
    return "\n".join(lines) + "\n"


def render_running_next_action(
    state: dict[str, Any],
    phase_log: Path,
    spec_path: Path,
) -> str:
    commands = [
        "python3 scripts/run_watchdog.py status",
        f"tail -n 80 {shlex.quote(str(phase_log))}",
    ]
    return "\n".join(
        [
            f"Run `{state['run_id']}` is active.",
            "",
            f"Current phase: `{state['phase_id']}`",
            f"Why: {state.get('phase_description', 'No phase description provided.')}",
            "",
            "Recommended commands:",
            *commands,
            "",
            f"Spec: {spec_path}",
        ]
    ) + "\n"


def render_failed_next_action(
    state: dict[str, Any],
    phase_log: Path,
    summary: str,
) -> str:
    commands = [
        f"tail -n 120 {shlex.quote(str(phase_log))}",
        "python3 scripts/run_watchdog.py status",
        f"python3 scripts/run_watchdog.py run {shlex.quote(state['spec_path'])}",
    ]
    return "\n".join(
        [
            f"Run `{state['run_id']}` failed.",
            "",
            f"Failure phase: `{state.get('phase_id')}`",
            summary,
            "",
            "Recommended commands:",
            *commands,
            "",
            "Policy: fix the failure on the current compute tier before retrying or promoting.",
        ]
    ) + "\n"


def render_success_next_action(
    state: dict[str, Any],
    phase_log: Path,
    spec: dict[str, Any],
) -> str:
    if state.get("status") == "dry-run-complete":
        lines = [
            f"Dry run for `{state['run_id']}` completed successfully.",
            "",
            "No phase commands were executed and no real logs were produced.",
            "",
            "Recommended commands:",
            f"python3 scripts/run_watchdog.py validate {shlex.quote(state['spec_path'])}",
            f"python3 scripts/run_watchdog.py run {shlex.quote(state['spec_path'])}",
        ]
        manual_next_spec = spec.get("manual_next_spec")
        if manual_next_spec:
            lines.extend(
                [
                    "",
                    f"After the real smoke run is clean, dry-run the next spec: python3 scripts/run_watchdog.py run {shlex.quote(manual_next_spec)} --dry-run",
                ]
            )
        return "\n".join(lines) + "\n"

    lines = [
        f"Run `{state['run_id']}` completed successfully.",
        "",
        spec.get("success_summary", "Review the run artifacts before making the next capital allocation decision."),
        "",
        "Recommended commands:",
        "python3 scripts/run_watchdog.py status",
        f"tail -n 120 {shlex.quote(str(phase_log))}",
    ]
    manual_next_command = spec.get("manual_next_command")
    if manual_next_command:
        lines.append(manual_next_command)
    manual_next_spec = spec.get("manual_next_spec")
    if manual_next_spec:
        lines.extend(
            [
                "",
                f"Next spec (manual, not automatic): {manual_next_spec}",
                f"Dry-run it first: python3 scripts/run_watchdog.py run {shlex.quote(manual_next_spec)} --dry-run",
            ]
        )
    lines.extend(
        [
            "",
            "Policy: do not auto-promote. Review runtime, artifact, legality, and logs before spending more compute.",
        ]
    )
    return "\n".join(lines) + "\n"


def phase_log_path(run_dir: Path, index: int, phase: dict[str, Any]) -> Path:
    log_name = phase.get("log_name") or f"{index:02d}_{phase['id']}.log"
    return run_dir / "logs" / log_name


def build_run_dir(paths: Paths, spec: dict[str, Any]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = paths.runs_dir / f"{stamp}_{spec['run_id']}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    return run_dir


def build_context(
    spec: dict[str, Any],
    spec_path: Path,
    run_dir: Path,
    state_dir: Path,
) -> dict[str, str]:
    base = {key: value for key, value in os.environ.items()}
    base.update(
        {
            "RUN_ID": str(spec["run_id"]),
            "SPEC_PATH": str(spec_path),
            "RUN_DIR": str(run_dir),
            "STATE_DIR": str(state_dir),
        }
    )
    resolved_env = expand_mapping(spec.get("env"), base)
    return {**base, **resolved_env}


def write_phase_artifacts(
    paths: Paths,
    state: dict[str, Any],
    heartbeat: dict[str, Any],
    next_action: str,
) -> None:
    atomic_write_json(paths.current_state, state)
    atomic_write_json(paths.heartbeat, heartbeat)
    atomic_write_text(paths.status_txt, render_status_text(state, heartbeat))
    atomic_write_text(paths.next_action, next_action)


def run_phase(
    *,
    index: int,
    phase: dict[str, Any],
    spec: dict[str, Any],
    spec_path: Path,
    run_dir: Path,
    paths: Paths,
    base_context: dict[str, str],
    state: dict[str, Any],
    dry_run: bool,
    heartbeat_interval_s: float,
) -> dict[str, Any]:
    phase_id = str(phase["id"])
    phase_log = phase_log_path(run_dir, index, phase)
    phase_context = {
        **base_context,
        "PHASE_ID": phase_id,
        "PHASE_LOG": str(phase_log),
    }
    phase_env = {**base_context, **expand_mapping(phase.get("env"), phase_context)}
    cwd_value = expand_value(str(phase.get("cwd", phase_env.get("REPO_DIR", "."))), phase_env)
    cwd = Path(cwd_value)
    command = expand_value(str(phase["command"]), phase_env)

    state.update(
        {
            "status": "running" if not dry_run else "dry-run",
            "phase_index": index,
            "phase_id": phase_id,
            "phase_description": phase.get("description"),
            "active_log": str(phase_log),
            "updated_at": utc_now(),
        }
    )
    heartbeat = {
        "run_id": spec["run_id"],
        "status": state["status"],
        "phase_id": phase_id,
        "updated_at": utc_now(),
        "pid": None,
        "last_output": [],
    }
    write_phase_artifacts(paths, state, heartbeat, render_running_next_action(state, phase_log, spec_path))
    append_jsonl(
        run_dir / "events.jsonl",
        {
            "event": "phase_started",
            "phase_id": phase_id,
            "timestamp": utc_now(),
            "command": command,
            "cwd": str(cwd),
            "dry_run": dry_run,
        },
    )

    if dry_run:
        append_jsonl(
            run_dir / "events.jsonl",
            {
                "event": "phase_dry_run_complete",
                "phase_id": phase_id,
                "timestamp": utc_now(),
            },
        )
        return {
            "phase_id": phase_id,
            "status": "dry-run",
            "command": command,
            "cwd": str(cwd),
            "log_path": str(phase_log),
            "started_at": utc_now(),
            "completed_at": utc_now(),
            "duration_s": 0.0,
            "exit_code": 0,
        }

    started_at = time.monotonic()
    started_at_utc = utc_now()
    tail_buffer: deque[str] = deque(maxlen=10)
    proc = subprocess.Popen(
        ["/bin/bash", "-lc", command],
        cwd=str(cwd),
        env=phase_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    pump = OutputPump(proc.stdout, phase_log, tail_buffer)
    pump.start()
    last_heartbeat = 0.0

    while True:
        now = time.monotonic()
        if now - last_heartbeat >= heartbeat_interval_s:
            heartbeat = {
                "run_id": spec["run_id"],
                "status": "running",
                "phase_id": phase_id,
                "updated_at": utc_now(),
                "pid": proc.pid,
                "last_output": list(tail_buffer),
            }
            state["updated_at"] = heartbeat["updated_at"]
            write_phase_artifacts(paths, state, heartbeat, render_running_next_action(state, phase_log, spec_path))
            last_heartbeat = now

        return_code = proc.poll()
        if return_code is not None:
            break
        time.sleep(1.0)

    pump.join(timeout=5)
    completed_at = time.monotonic()
    completed_at_utc = utc_now()
    duration_s = round(completed_at - started_at, 3)
    phase_result = {
        "phase_id": phase_id,
        "status": "complete" if return_code == 0 else "failed",
        "command": command,
        "cwd": str(cwd),
        "log_path": str(phase_log),
        "started_at": started_at_utc,
        "completed_at": completed_at_utc,
        "duration_s": duration_s,
        "exit_code": int(return_code),
    }
    append_jsonl(
        run_dir / "events.jsonl",
        {
            "event": "phase_completed",
            "phase_id": phase_id,
            "timestamp": completed_at_utc,
            "status": phase_result["status"],
            "exit_code": return_code,
            "duration_s": duration_s,
        },
    )
    return phase_result


def handle_run(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec).resolve()
    spec = load_spec(spec_path)
    state_dir = Path(args.state_dir).resolve()
    paths = build_paths(state_dir)
    ensure_base_state(paths)
    acquire_lock(paths, str(spec["run_id"]))

    try:
        run_dir = build_run_dir(paths, spec)
        base_context = build_context(spec, spec_path, run_dir, state_dir)
        state: dict[str, Any] = {
            "run_id": spec["run_id"],
            "spec_path": str(spec_path),
            "hypothesis": spec["hypothesis"],
            "parent_branch": spec["parent_branch"],
            "track": spec["track"],
            "compute_tier": spec["compute_tier"],
            "promotion_gate": spec.get("promotion_gate"),
            "auto_promote": False,
            "manual_next_spec": spec.get("manual_next_spec"),
            "status": "starting",
            "phase_index": None,
            "phase_id": None,
            "phase_description": None,
            "run_dir": str(run_dir),
            "active_log": None,
            "started_at": utc_now(),
            "updated_at": utc_now(),
            "phase_results": [],
        }
        heartbeat = {
            "run_id": spec["run_id"],
            "status": "starting",
            "updated_at": utc_now(),
            "message": "Run created; watchdog is preparing phases.",
        }
        write_phase_artifacts(
            paths,
            state,
            heartbeat,
            "Run created.\n\nRecommended command:\npython3 scripts/run_watchdog.py status\n",
        )

        append_jsonl(
            run_dir / "events.jsonl",
            {
                "event": "run_started",
                "run_id": spec["run_id"],
                "timestamp": utc_now(),
                "spec_path": str(spec_path),
                "dry_run": bool(args.dry_run),
            },
        )
        atomic_write_json(run_dir / "spec_snapshot.json", spec)

        for index, phase in enumerate(spec["phases"], start=1):
            phase_result = run_phase(
                index=index,
                phase=phase,
                spec=spec,
                spec_path=spec_path,
                run_dir=run_dir,
                paths=paths,
                base_context=base_context,
                state=state,
                dry_run=bool(args.dry_run),
                heartbeat_interval_s=float(args.heartbeat_interval),
            )
            state["phase_results"].append(phase_result)
            state["updated_at"] = utc_now()

            if phase_result["status"] == "failed":
                summary = phase.get(
                    "failure_summary",
                    "Inspect the phase log, fix the concrete blocker, and rerun on the same compute tier.",
                )
                state["status"] = "failed"
                heartbeat = {
                    "run_id": spec["run_id"],
                    "status": "failed",
                    "phase_id": phase_result["phase_id"],
                    "updated_at": utc_now(),
                    "pid": None,
                    "last_output": [],
                }
                write_phase_artifacts(
                    paths,
                    state,
                    heartbeat,
                    render_failed_next_action(state, Path(phase_result["log_path"]), summary),
                )
                terminal = {
                    "run_id": spec["run_id"],
                    "status": "failed",
                    "updated_at": utc_now(),
                    "failed_phase": phase_result["phase_id"],
                    "log_path": phase_result["log_path"],
                    "summary": summary,
                    "run_dir": str(run_dir),
                    "phase_results": state["phase_results"],
                }
                atomic_write_json(paths.terminal_result, terminal)
                atomic_write_json(run_dir / "terminal_result.json", terminal)
                return 1

        final_log = Path(state["phase_results"][-1]["log_path"])
        state["status"] = "dry-run-complete" if args.dry_run else "complete"
        state["phase_id"] = None
        state["phase_description"] = None
        state["active_log"] = str(final_log)
        state["updated_at"] = utc_now()
        heartbeat = {
            "run_id": spec["run_id"],
            "status": state["status"],
            "updated_at": utc_now(),
            "message": "All phases finished.",
        }
        write_phase_artifacts(
            paths,
            state,
            heartbeat,
            render_success_next_action(state, final_log, spec),
        )
        terminal = {
            "run_id": spec["run_id"],
            "status": state["status"],
            "updated_at": utc_now(),
            "run_dir": str(run_dir),
            "phase_results": state["phase_results"],
            "summary": spec.get("success_summary"),
        }
        atomic_write_json(paths.terminal_result, terminal)
        atomic_write_json(run_dir / "terminal_result.json", terminal)
        return 0
    finally:
        release_lock(paths)


def handle_status(args: argparse.Namespace) -> int:
    paths = build_paths(Path(args.state_dir).resolve())
    ensure_base_state(paths)
    state = read_json(paths.current_state)
    heartbeat = read_json(paths.heartbeat)
    sys.stdout.write(render_status_text(state, heartbeat))
    return 0


def handle_next(args: argparse.Namespace) -> int:
    paths = build_paths(Path(args.state_dir).resolve())
    ensure_base_state(paths)
    sys.stdout.write(paths.next_action.read_text(encoding="utf-8"))
    return 0


def handle_validate(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec).resolve()
    spec = load_spec(spec_path)
    payload = {
        "spec_path": str(spec_path),
        "run_id": spec["run_id"],
        "track": spec["track"],
        "compute_tier": spec["compute_tier"],
        "phases": [phase["id"] for phase in spec["phases"]],
        "status": "valid",
    }
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pod-local watchdog for reproducible Parameter Golf runs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Execute a run spec with durable state files.")
    run_parser.add_argument("spec", help="Path to the JSON run spec.")
    run_parser.add_argument(
        "--state-dir",
        default="11_RUN_CONTROL",
        help="Directory where durable watchdog state will be written.",
    )
    run_parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=15.0,
        help="Seconds between heartbeat updates while a phase is running.",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the spec and write scaffold state without executing commands.",
    )
    run_parser.set_defaults(func=handle_run)

    status_parser = subparsers.add_parser("status", help="Print the current watchdog status.")
    status_parser.add_argument("--state-dir", default="11_RUN_CONTROL")
    status_parser.set_defaults(func=handle_status)

    next_parser = subparsers.add_parser("next", help="Print the current recommended next action.")
    next_parser.add_argument("--state-dir", default="11_RUN_CONTROL")
    next_parser.set_defaults(func=handle_next)

    validate_parser = subparsers.add_parser("validate", help="Validate a run spec without running it.")
    validate_parser.add_argument("spec", help="Path to the JSON run spec.")
    validate_parser.set_defaults(func=handle_validate)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        raise
    except WatchdogError as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
