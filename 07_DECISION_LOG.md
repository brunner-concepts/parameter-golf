# Decision Log

## 2026-03-23 — Project bootstrap

**Decision:** Initialize three-track portfolio targeting accepted record.

**Rationale:** 
- Official SOTA is 1.1428 (PR #180). Pending PRs are significantly lower but not yet accepted.
- #505 (GEPA, 1.1181) is the strongest non-TTT base. Legal TTT has not been attempted on it.
- #508 (1.1215) validates legal TTT on the #414 family.
- Combining the strongest base with the proven legal TTT recipe is the highest-EV path.
- Track B provides insurance via the more mature #414 stack.

**Track allocation:** 60% A / 30% B / 10% C

**Immediate next actions:**
1. Extract exact configs from #414, #505, #508
2. Set up compute environment (RunPod 8×H100 SXM)
3. Begin reproduction wave

## 2026-03-23 — Source-backed repro prep before first run

**Decision:**
Treat local work as control-plane preparation only: verify frontier state from primary sources, sync exact PR artifacts for #414/#505/#508 without relying on local git fetches, and add a static legality audit for score-first TTT.

**Rationale:**
- This sandbox cannot run reproductions: no `torch`, no CUDA, no FineWeb shards, and `.git` writes are blocked.
- The win condition is chronology plus defensibility, so ambiguity in reproduction inputs and TTT ordering is the highest avoidable risk before spending 8×H100 time.
- PR #505, #508, and #414 remain open on March 23, 2026; the official README leaderboard is still topped by 1.1428, so fast, exact reproduction remains the highest-EV path.

**Consequences:**
1. Use `scripts/sync_repro_targets.py` to materialize exact upstream record files and a manifest on the compute host.
2. Use `scripts/audit_ttt_legality.py` against any TTT branch before keeping it alive.
3. Do not start Track A creative transfer work until two mandatory reproductions land within tolerance.

## 2026-03-23 — Durable watchdog control plane before first 8x repro

**Decision:**
Add a pod-local watchdog, durable run specs, and run-state files before the first 8x H100 SXM reproduction.

**Rationale:**
- The controller interface is turn-based, but the GPU jobs are not. Durable files are required to preserve exact state, failure reasons, and next commands across sessions.
- Reproduction-first strategy loses value if each pod run depends on ad hoc shell state or implicit memory.
- The watchdog must help execution without becoming a second decision-maker, so auto-promotion stays forbidden.

**Consequences:**
1. Use `scripts/run_watchdog.py` plus `run_specs/*.json` to launch smoke/full reproduction jobs.
2. Persist liveness and next commands under `11_RUN_CONTROL/`.
3. Treat watchdog success as operational evidence only; promotion still requires human/controller review against the project gates.

## 2026-03-23 — PR #414 smoke path is operational, but not publishable

**Decision:**
Treat the completed 1xH100 SXM smoke run as infrastructure validation only. Do not interpret the BPB as frontier evidence and do not publish it.

**Rationale:**
- The smoke run completed end-to-end: FlashAttention-3 bootstrap, data download, training loop, EMA evaluation, and artifact packaging all worked.
- The run was intentionally truncated to 120 seconds on a single GPU and one train shard, so the resulting `val_bpb: 1.7547` is not remotely comparable to the published `1.1233`.
- The final int6 roundtrip collapsed to `6.1321` BPB, which is a strong signal that smoke-scale quantized numbers are not useful for promotion decisions.

**Consequences:**
1. Scoreboard / PR answer remains **no**: nothing from this project is publishable yet.
2. The operational blocker moved from "can the stack run at all?" to "can the full managed 8x repro hit the claimed score within tolerance?"
3. Next highest-EV action is a managed full PR #414 repro on 8x H100 SXM, ideally after pushing the watchdog scaffold and preserving the flash-attention bootstrap tax.

## 2026-03-23 — Off-pod mirroring is mandatory for expensive runs

**Decision:**
Treat local mirroring, summary generation, and optional notifications as part of the standard launch path for any materially expensive RunPod experiment.

**Rationale:**
- The first 8x PR #414 repro proved the training path can run, but the pod later exited on the provider side and terminal certainty was weaker than it should have been.
- Pod-local watchdog state is necessary but not sufficient; the controller also needs off-pod copies of status, active log tail, and terminal state.
- Better observability is a higher-EV investment than adding more autonomy or more speculative branches right now.

**Consequences:**
1. Launches should use `scripts/launch_runpod_managed_run.py` where possible.
2. `scripts/mirror_runpod_watchdog.py` should mirror `status.txt`, `current_state.json`, `heartbeat.json`, `terminal_result.json`, and the active log tail into `11_RUN_CONTROL/live/<run_id>/`.
3. The next full 8x repro should not rely on pod-local files alone for progress visibility or post-mortem certainty.

## 2026-03-23 — Nissanbox operator mode becomes the preferred control plane

**Decision:**
Implement a Nissanbox-centered operator loop: Docker-isolated supervisor, Telegram-capable mirroring, a private dashboard, and one automatic same-spec retry for infra/provider exits.

**Rationale:**
- The controller needs a durable, always-on host that is not this laptop.
- The project benefits from automation at the execution layer, not at the research-direction layer.
- One guarded retry on the same approved spec increases resilience without violating the compute-allocation rules.

**Consequences:**
1. Preferred entrypoint becomes `scripts/operator_supervisor.py`, not raw pod launch commands.
2. `scripts/mirror_runpod_watchdog.py` now owns event history and Telegram/webhook notifications in addition to file mirroring.
3. `scripts/serve_run_control_dashboard.py`, `docker-compose.nissanbox.yml`, and `ops/nissanbox/README.md` define the standard Nissanbox operator deployment.

## 2026-03-24 — Supervisor retry path validated against provider-side pre-SSH failures

**Decision:**
Keep one automatic same-spec retry for infra/provider exits, and add short remote-launch retries inside a single pod before escalating to a full spec retry.

**Rationale:**
- A live smoke validation hit two provider-side failures before the watchdog could begin useful work: one pod never reached SSH readiness, and a second closed the first remote SSH command immediately after host-key acceptance.
- The new supervisor correctly classified the first event as launch failure and scheduled the single allowed retry.
- Launch resilience should improve inside the pod first before consuming the whole same-spec retry budget.

**Consequences:**
1. `scripts/launch_runpod_managed_run.py` should retry the initial remote watchdog launch a few times before giving up on the pod.
2. Provider-side pre-SSH failures remain an infra risk, not a reason to change the research thesis.
3. The next full repro should still use the Nissanbox operator path, but be interpreted with explicit awareness of provider readiness noise.

## 2026-03-24 — PR #414 managed smoke exposed a bad FlashAttention ref, not a model failure

**Decision:**
Treat the latest managed `repro_pr414_smoke` failure as a bootstrap-control-plane bug. Stop the pod immediately, pin FlashAttention to a real upstream commit, and rerun smoke on the same cheap compute tier before spending on 8x.

**Rationale:**
- The smoke run reached the pod-local watchdog and mirrored state correctly, so the autonomous control loop is now operational.
- The terminal failure came from `scripts/bootstrap_runpod_env.sh` attempting `git checkout v3.0.0` inside `flash-attention`, but the upstream repo does not currently publish a `v3.0.0` tag.
- This is execution drift in our bootstrap assumptions, not evidence against PR #414 or the broader research plan.

**Consequences:**
1. Pin `FLASH_ATTN_REF` in both PR #414 run specs and the bootstrap script to a real, reproducible upstream commit.
2. Keep the research sequence unchanged: `#414 -> #508`, then only revisit Track A transfer work.
3. Continue using low-cost smoke validation to clear infra bugs before any 8x H100 SXM spend.

## 2026-03-24 — Managed PR #414 smoke now completes, but bootstrap tax dominates economics

**Decision:**
Treat the corrected managed smoke as a successful operational validation and a failed economic validation. Do not launch the 8x H100 SXM reproduction until the FlashAttention bootstrap cost is reused or eliminated.

**Rationale:**
- The managed smoke completed end-to-end on 1x H100 PCIe: watchdog, mirror, dashboard, data download, training loop, EMA path, evaluation, and artifact packaging all worked.
- The run remained non-publishable scientifically: `val_bpb: 1.9565` at the 120s stop and `final_int6_sliding_window val_bpb: 5.6011` are smoke-only numbers, not frontier evidence.
- The important quantitative finding is operational economics: `bootstrap_env` took `7709.693s`, far larger than the actual smoke phase (`987.907s`). Rebuilding FlashAttention from source on every pod would destroy EV, especially on 8x H100 SXM.

**Consequences:**
1. Preserve or transfer the completed FlashAttention build from the smoke pod before stopping it, or otherwise create a reusable warm-start path.
2. Keep the next scientific target unchanged: full managed PR #414 reproduction, but only after the FA bootstrap tax is amortized.
3. Continue treating smoke BPBs as infra evidence only; no scoreboard or promotion claim is justified yet.
