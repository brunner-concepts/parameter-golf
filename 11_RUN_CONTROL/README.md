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
