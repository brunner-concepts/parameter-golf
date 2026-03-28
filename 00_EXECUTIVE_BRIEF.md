# Executive Brief

## Goal

Ship the earliest legally defensible PR that is accepted as the new official record in OpenAI Parameter Golf.

## Current target to beat

Official SOTA: **1.1194 BPB** (PR #549, merged March 24, 2026)
Best pending record-eligible submission: **0.0804 BPB** (#933, CacheMoney, 3-seed mean, March 27, 2026)
Best conservative stepping-stone cache submission: **0.1181 BPB** (#868, Budgeted Two-Pass N-gram Backoff)

To land an accepted record, the submission must beat the official SOTA by ≥0.005 nats at p < 0.01.

## Track allocation

| Track | Allocation | Target | Status |
|-------|-----------|--------|--------|
| **A: record-eligible eval cache** | 70% | Reproduce a score-first n-gram / phrase cache path in the `#868` / `#913` family | Not started |
| **B: control-plane + fallback neural anchor** | 20% | Keep the watchdog, mirroring, and warm-start path reliable; use `#414` only as a fallback anchor if still needed | Warm-start validated; full repro paused |
| **C: longer-shot neural research** | 10% | GEPA + legal TTT or tiny micro-deltas only after the cache route is understood | Not started |

## Top 3 hypotheses

1. The shortest accepted-record route now runs through the cache frontier (`#933`, `#868`, and related lineage), not further pure-neural tuning.
2. The current control plane is good enough to support serious runs: watchdog, mirroring, and FlashAttention warm-start are no longer the main blockers.
3. Two-pass full-rescore cache variants are now the strongest live route, but they carry explicit legality scrutiny; conservative score-first cache paths may still maximize accepted-record probability.

## Stop/go rules

- **STOP** any branch where single-seed fails to beat parent by ≥0.001 BPB
- **STOP** any branch where step time increases >5% without compensating BPB gain
- **STOP** any branch where artifact exceeds 15.9 MB after packaging
- **STOP** spending more on pure-neural `#414` reproduction as a record path unless it directly informs the cache route or packaging
- **GO** to 3-seed only when single-seed clears promotion threshold
- **GO** to PR packaging immediately when 3-seed mean clears accepted-record territory
