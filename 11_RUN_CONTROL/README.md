# Run Control

`11_RUN_CONTROL/` is the durable bridge between turn-based agent sessions and long-running pod jobs.

It exists so the project does not rely on transient chat state for:

- current run phase
- last heartbeat
- terminal failure reason
- exact next recommended command

## Files

- `current_state.json`: canonical current run state
- `heartbeat.json`: most recent liveness update while a phase is running
- `status.txt`: human-readable summary
- `next_action.txt`: exact next command(s) to run
- `terminal_result.json`: final outcome of the last completed/failed run
- `runs/`: immutable per-run snapshots, logs, and event streams

## Policy

- The watchdog may execute a run spec, but it may not auto-promote to a more expensive tier.
- Every run must remain auditable from files on disk alone.
- Promotion decisions still belong to the controller, not the watchdog.

## Main commands

```bash
python3 scripts/run_watchdog.py validate run_specs/repro_pr414_smoke.json
python3 scripts/run_watchdog.py run run_specs/repro_pr414_smoke.json --dry-run
python3 scripts/run_watchdog.py status
python3 scripts/run_watchdog.py next
```

## Local visibility layer

The watchdog is pod-local. To make long runs visible from this Mac without relying on chat memory:

```bash
python3 scripts/mirror_runpod_watchdog.py \
  --pod-id <runpod-pod-id> \
  --remote-state-dir /workspace/run_control \
  --local-dir 11_RUN_CONTROL/live/<run_id> \
  --notify-macos
```

This mirrors:

- `pod.json`
- `current_state.json`
- `heartbeat.json`
- `status.txt`
- `next_action.txt`
- `terminal_result.json`
- `active_log.tail.txt`
- `summary.md`

`summary.md` is the highest-signal file to open when checking a run.

## One-command launch

For managed launches that create the pod, start the watchdog remotely, and detach the local mirror:

```bash
python3 scripts/launch_runpod_managed_run.py run_specs/repro_pr414_full.json --notify-macos
```

This is intentionally not fully autonomous:

- it refuses to launch when balance is below the tier minimum
- it starts exactly one requested spec
- it does not auto-promote to a more expensive run
- final stop/go decisions still belong to the controller
