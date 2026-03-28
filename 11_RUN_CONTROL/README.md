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
- `events.jsonl`
- `current_state.json`
- `heartbeat.json`
- `status.txt`
- `next_action.txt`
- `terminal_result.json`
- `active_log.tail.txt`
- `summary.md`

`summary.md` is the highest-signal file to open when checking a run.

## Guardrailed launch

For a single approved spec with local mirroring:

```bash
python3 scripts/launch_runpod_managed_run.py run_specs/repro_pr414_full.json --notify-macos
```

For hands-off execution with one automatic same-spec infra retry:

```bash
python3 scripts/operator_supervisor.py run_specs/repro_pr414_full.json
```

This is intentionally not fully autonomous:

- it refuses to launch when balance is below the tier minimum
- it starts exactly one requested spec
- it may retry the same approved spec once after an infra/provider exit with no clean terminal result
- it does not auto-promote to a more expensive or different run
- final stop/go decisions still belong to the controller

## Dashboard

Serve the live mirror directory privately:

```bash
python3 scripts/serve_run_control_dashboard.py --host 127.0.0.1 --port 8787
```

Useful routes:

- `/` — all mirrored runs
- `/runs/<run_id>` — one run detail page
- `/api/runs` — JSON for automation

## Local operator mode

The preferred sandboxed local operator now runs through:

- `docker-compose.local-operator.yml`
- `ops/local-operator/README.md`
- `scripts/control_plane_daemon.py`

This adds:

- budget-aware frontier polling
- guarded auto-generation of the current cache-route repro specs
- executive state under `11_RUN_CONTROL/control_plane/state/executive_state.json`
- durable executive memory in `11_RUN_CONTROL/control_plane/state/working_memory.md`
- decision history in `11_RUN_CONTROL/control_plane/state/decisions.jsonl`
- actual billed-spend accounting instead of naive launch reservations
- provider-side staging via RunPod network volumes for reusable FlashAttention assets
- queue state under `11_RUN_CONTROL/control_plane/state/`
- a single localhost-only dashboard that shows both control-plane state and live run mirrors

The older Nissanbox scaffold still exists, but it is no longer the primary recommendation.

## Executive autonomy

The control plane is no longer just a queue runner.

It now has an executive layer that may:

- diagnose infra bottlenecks and encode them into harsher policy
- pivot launch topology within the approved target family
- seed provider-side storage so the Mac upload path is no longer on the hot path for full repros
- continue operating until it hits an explicit budget, legality, or reserve-floor stop condition

It may not:

- invent a new research lane outside the approved target family
- widen legality risk automatically
- auto-push or auto-open PRs
- ignore the artifact/runtime/legality gates

## Telegram control room

Telegram is now a control-room gateway over the same durable state.

Because the conversational layer uses the locally authenticated Codex CLI, the Telegram gateway runs as a host-side sidecar (`scripts/telegram_sidecar.py`), while the operator itself remains sandboxed in Docker.

Useful commands:

- `status`
- `strategy`
- `next`
- `why`
- `decision`
- `budget`
- `pause`
- `resume`
- `cap <usd>`

Freeform chat still routes through Codex, but these commands mutate or report real local operator state directly.
