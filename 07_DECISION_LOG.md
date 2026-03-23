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
