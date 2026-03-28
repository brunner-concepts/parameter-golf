# System Architecture

## Agent roles

### 1. Chief of Staff / Program Manager

Owns: source of truth files, experiment queue, stop/go decisions, branch naming, artifact hygiene, final PR packaging.
Never writes model code. Only coordinates.

### 2. Frontier Intelligence Agent

Owns: syncing 02_FRONTIER_STATE.md, extracting hyperparams from public PRs, identifying legality risk, producing delta memos when frontier moves.
Only reads public sources and updates the internal brief.

### 3. Reproduction Agent

Owns: exact reproduction of known bases, no creative changes, branch purity, matching reported config and artifact size.
Most important worker at the start.

### 4. Architecture Agent

Owns: localized model changes, one hypothesis per branch, explicit latency/byte budget, implementation notes.

### 5. Training Systems Agent

Owns: throughput, kernel choices, memory behavior, profiling, eval-time runtime budget.

### 6. Quantization / Packaging Agent

Owns: quant tax, export path, GPTQ/QAT knobs, zstd profile, artifact byte accounting.

### 7. Evaluation Agent

Owns: exact measurement, step time, pre/post-quant BPB, legal TTT protocol enforcement, seed aggregation.

### 8. Submission Agent

Owns: record eligibility checklist, concise PR description, logs/artifacts/plots/checksums.

### 9. Run Control / Watchdog

Owns: pod-local phase execution, heartbeats, durable run state, failure capture, and next-command suggestions.
Never auto-promotes to a more expensive compute tier. Never overrides the promotion gates.
Pairs with a local mirror/notifier layer that copies run state off-pod so expensive runs remain observable even if the provider exits the machine.
Recommended deployment target is the local guardrailed operator container (`docker-compose.local-operator.yml`) that owns RunPod launch, control-plane state, and the private dashboard. A remote always-on host remains optional, not required.

### 10. Executive Operator

Owns: diagnosis, topology pivots, provider-side staging, budget overrides within policy, and executive memory.
This layer sits above the queue/supervisor/watchdog stack and is responsible for keeping the system moving without waiting for the user on ordinary infra failures.
It may change execution topology inside the approved target family, but it may not widen research scope, ignore legality gates, or exceed balance-reserve rules.

## Execution phases

### Phase 0: Bootstrap
- Fork upstream, pin commit hash
- Mirror rules into 01_RULES_AND_LEGALITY.md
- Ingest frontier state into 02_FRONTIER_STATE.md
- Generate first hypothesis queue

### Phase 1: Mandatory reproductions
Execute in order:
1. Reproduce #414 (standard non-TTT)
2. Reproduce #508 or #503 (legal TTT on standard stack)
3. Reproduce #505 (GEPA no-TTT)

No branching until at least two are within tolerance.

### Phase 2: Confidence intervals
For each reproduced base:
1. 1 quick smoke run
2. 1 full proper run
3. 3-seed only if promotion threshold crossed

### Phase 3: Portfolio execution
Run parallel branches:
- `trackA/gepa-legal-ttt`
- `trackB/std414-legal-ttt`
- `trackC/microdelta-only`

### Phase 4: Ruthless culling
Kill any branch that fails gates.

### Phase 5: PR-first behavior
If a branch plausibly clears accepted-record territory, stop searching and package immediately.

## Recursive feedback

Each agent writes a structured report after every run:
- hypothesis, parent branch, exact diff
- train step time, eval time, artifact size
- pre-quant BPB, post-quant BPB
- legality risk
- recommendation: promote / kill / revise

Chief of Staff then updates: 05_HYPOTHESIS_BACKLOG.jsonl, 06_EXPERIMENT_REGISTRY.jsonl, 07_DECISION_LOG.md

No agent gets to self-promote its own idea.

The watchdog additionally persists:
- `11_RUN_CONTROL/current_state.json`
- `11_RUN_CONTROL/heartbeat.json`
- `11_RUN_CONTROL/next_action.txt`
- immutable per-run logs under `11_RUN_CONTROL/runs/`

The local mirror additionally persists:
- `11_RUN_CONTROL/live/<run_id>/summary.md`
- `11_RUN_CONTROL/live/<run_id>/active_log.tail.txt`
- `11_RUN_CONTROL/live/<run_id>/pod.json`
- `11_RUN_CONTROL/live/<run_id>/events.jsonl`
- `11_RUN_CONTROL/live/<run_id>/supervisor_state.json`

The Nissanbox operator additionally owns:
- `scripts/operator_supervisor.py` for same-spec infra retries
- `scripts/serve_run_control_dashboard.py` for private status visualization
- Telegram/webhook notifications for meaningful run transitions

The local operator additionally owns:
- `scripts/control_plane_daemon.py` for frontier polling, budget governance, target ranking, and guarded auto-launch of approved specs only
- `scripts/repair_controller.py` for host-side deterministic self-repair, automatic parity reviews, and bounded patch/validate/audit/relaunch loops
- `scripts/provider_storage_manager.py` for provider-side staging on RunPod network volumes
- `11_RUN_CONTROL/control_plane/state/executive_state.json` for the current diagnosis, next autonomous action, and provider-storage readiness
- `11_RUN_CONTROL/control_plane/state/working_memory.md` for a human-readable executive summary
- `11_RUN_CONTROL/control_plane/state/decisions.jsonl` for durable executive decisions and topology pivots
- `11_RUN_CONTROL/control_plane/state/repair_queue.json` and `repair_journal.jsonl` for the current repair lane and its audit trail
- `11_RUN_CONTROL/control_plane/` for policy, generated specs, advisory memos, and runtime snapshots

## Control hierarchy

The runtime org chart is now:

1. `User / board` — capital allocator and final authority
2. `Executive operator` — strategy, diagnosis, topology pivots, budget-aware autonomy
3. `Repair controller` — deterministic self-repair, parity review, guarded auto-push, and relaunch ownership
4. `Control plane daemon` — queue evaluation, spend checks, launch orchestration
5. `Operator supervisor` — same-spec infra retries and launch ownership
6. `Run watchdog` — pod-local phase execution and terminal evidence
7. `Mirror / Telegram / dashboard` — visibility and external reporting only

This keeps the actual execution loop autonomous while making every state transition auditable from files on disk.
