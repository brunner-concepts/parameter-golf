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
