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

## 2026-03-24 — Official frontier moved; Track B target must update from #508-era thinking to #549/#606/#615

**Decision:**
Adjust research sequencing, not away from the `#414` family, but away from stale March 23 assumptions. Keep the immediate next action as a warm-started full `#414` repro, then target the accepted `#549` family and the live `#606/#615/#634` frontier rather than treating `#508` as the current Track B destination.

**Rationale:**
- The upstream README now lists `1.1194` from PR `#549` as the official accepted leaderboard leader, merged on March 24, 2026.
- The live tracker now shows several stronger pending runs: `#606` at `1.1162`, `#615` at `1.1169`, `#634` at `1.1171`, and `#626` at `1.1180`.
- PR `#609` was reclassified as non-record because GPTQ calibration happened outside the allowed budget. This changes how we should evaluate Full GPTQ paths: lower BPB is not enough without clean budget accounting.
- Therefore, reproducing `#414` remains useful as a delta anchor, but reproducing `#508` alone is no longer enough to define the shortest winning Track B route.

**Consequences:**
1. Update project memory so future sessions do not optimize against the stale `1.1428` / `#508` frontier.
2. Keep the next compute action unchanged: use the FA warm-start to run the full managed `#414` repro.
3. After `#414` repro, prioritize accepted-stack / live-frontier Track B work (`#549`, `#606`, `#615`, `#634`) ahead of historical `#508` hardening.

## 2026-03-25 — FlashAttention warm-start is validated

**Decision:**
Treat FlashAttention warm-start as solved enough for expensive runs. Do not spend more engineering time on source-build avoidance unless it directly improves the cache-route execution loop.

**Rationale:**
- The managed `validate_fa3_warm_start_pr414` run completed successfully on 1x H100 PCIe.
- Bootstrap finished in `345.076s`, down from the prior `7709.693s` source-build path.
- The remote log showed `flash_attn_interface already available`, which confirms the cached payload restored correctly.

**Consequences:**
1. The FlashAttention bootstrap tax is no longer a reason to delay serious runs.
2. Future infra work must justify itself against the new frontier, not against the old `#414` blocker.
3. The validation pod should be stopped immediately after terminal completion to avoid idle burn.

## 2026-03-27 — The cache frontier supersedes pure-neural work as the shortest winning route

**Decision:**
Pause `#414` full reproduction as the default next action and pivot the project’s highest-priority lane toward reproducing a record-eligible backward-looking cache path in the `#868` / `#913` family.

**Rationale:**
- Issue `#140` was updated on March 26, 2026 and reports a live record-eligible frontier of `0.0887` on PR `#913`, with several additional cache submissions in the `0.0935–0.1181` range.
- PR `#913` claims a `622 KB` artifact, `122s` train time, and `403s` eval time with only a tiny baseline model plus an eval-time cache layer.
- Against that frontier, a faithful `#414` repro at `1.1233` is no longer a serious route to an accepted record. It remains useful only as a fallback engineering anchor.

**Consequences:**
1. Project memory must stop describing `#414 -> #549/#606/#615` as the shortest winning Track B route.
2. Highest-priority reproduction work becomes exact upstream sync and evaluation of conservative, record-eligible cache methods.
3. Pure-neural lanes (`#414`, `#505`, GEPA + TTT, micro-deltas) should remain paused unless they directly support the cache route or a packaging fallback.

## 2026-03-28 — #933 becomes the top live target, but not automatically the safest first target

**Decision:**
Treat PR `#933` as the strongest live target to understand, but keep a conservative cache reproduction (`#868`) as the likely first route to spend serious reproduction compute on until the two-pass legality question is clearer.

**Rationale:**
- Issue `#140` updated on March 27, 2026 now lists `#933` at `0.0804` as the top record-eligible pending submission.
- PR `#933` itself explicitly says the legality of its two-pass full-rescore evaluation is under active discussion.
- Therefore, `#933` is the highest-upside frontier target, but not automatically the best first accepted-record bet.

**Consequences:**
1. Sync `#933` artifacts immediately so the repo can inspect them exactly.
2. Keep the operator/control plane narrow and reliable; do not respond to frontier motion by building a larger autonomous daemon.
3. Choose reproduction order based on accepted-record probability, not just raw BPB.

## 2026-03-28 — Launch reliability now gets hard timeouts and automatic recycle behavior

**Decision:**
Tighten the operator loop so launch phases are no longer allowed to hang indefinitely. Treat `pod running` as insufficient evidence; a launch must prove forward motion via successful phase completion or mirrored watchdog state within bounded time.

**Rationale:**
- The `#868` full repro hit the worst operational failure mode: 8x H100 pods were alive, but the job was stuck in launch (`copying_flash_attn_cache`) without producing experiment evidence.
- We also hit two concrete infra failures on the same route: a non-git `/workspace/parameter-golf` directory causing remote bootstrap failure, and an SSH/SCP disconnect during FlashAttention cache transfer.
- Those failures are execution problems, not research-thesis problems, so the system needs harsher launch-time controls rather than more idea generation.

**Consequences:**
1. Add explicit timeouts for SSH setup, spec copy, FlashAttention cache copy, and remote watchdog launch.
2. Make remote bootstrap idempotent by deleting a non-git `/workspace/parameter-golf` before recloning.
3. Raise the daily RunPod cap enough to permit one more serious 8x repro after failed launch tax, while keeping the single-run concurrency gate intact.

## 2026-03-28 — FlashAttention transport, not model logic, was the live bottleneck

**Decision:**
Cut the FlashAttention cache transport from a raw `1.5 GB` tarball to a compressed `.tar.zst` payload and add stale-launch pod recycling so the operator can kill orphaned 8x launches automatically.

**Rationale:**
- Inspection of the cached FlashAttention payload showed the bottleneck was a single unstripped `_C.abi3.so` with debug info; compressing the tarball reduced transport size to roughly `380 MB`.
- The previous raw-tar path caused repeated 8x launch failures (`scp` timeout / disconnect) before any remote watchdog state or experiment evidence existed.
- After a daemon restart, a live 8x pod could remain running even though no supervisor owned it anymore. That is unacceptable dead spend and must self-heal.

**Consequences:**
1. Default all future FlashAttention transfers to the compressed `.tar.zst` artifact and restore it directly in bootstrap.
2. Recycle any active pod stuck in a launch phase without a live supervisor after a short stale timeout.
3. Treat launch transport and supervisor ownership as first-class operator health signals, not just pod liveness.

## 2026-03-28 — Autonomous Operator V2 pivots from local upload retries to provider-side staging

**Decision:**
Promote the operator from a guarded retry loop into an executive control plane with provider-side staging, actual billed-spend accounting, and a Telegram control-room surface.

**Rationale:**
- The repeating failure mode is no longer research ambiguity; it is transport architecture. Re-copying even a compressed FlashAttention cache from the Mac to fresh 8x pods is still too fragile.
- The prior budget model counted launch reservations instead of actual billed spend, which made the operator simultaneously overconfident in some places and too timid in others.
- The prior Telegram layer exposed snapshots but did not expose the executive state or provide direct pause/resume/cap controls, which made the user an unnecessary bottleneck.

**Consequences:**
1. Full repros should prefer a seeded RunPod network volume over Mac-to-pod FlashAttention cache copies.
2. `budget_state.json` should be driven by real RunPod billing history plus reserve checks, not only by launch reservations.
3. `executive_state.json`, `working_memory.md`, and `decisions.jsonl` become first-class memory artifacts for the autonomous operator.
4. Telegram becomes a control room over the executive layer, with deterministic `pause`, `resume`, `budget`, `why`, `decision`, and `cap` commands in addition to conversational Codex turns.
