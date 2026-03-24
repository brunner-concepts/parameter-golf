# Executive Brief

## Goal

Ship the earliest legally defensible PR that is accepted as the new official record in OpenAI Parameter Golf.

## Current target to beat

Official SOTA: **1.1194 BPB** (abaybektursun, PR #549, merged March 24, 2026)
Best pending non-TTT: **1.1171 BPB** (#634, XSA-all + Full GPTQ + Parallel Muon + Selective Pruning, 3-seed)
Best pending legal TTT: **1.1162 BPB** (#606, int5 GPTQ + Soft-Round QAT + legal TTT, 3-seed)

To land an accepted record, the submission must beat the official SOTA by ≥0.005 nats at p < 0.01.

## Track allocation

| Track | Allocation | Target | Status |
|-------|-----------|--------|--------|
| **A: GEPA + legal TTT** | 60% | Port legal score-first TTT onto #505 GEPA base | Not started |
| **B: accepted-stack hardening** | 30% | Reproduce #414, then target the accepted #549 / live #606-#615 frontier | Smoke operational; full repro pending |
| **C: Micro-deltas** | 10% | Tiny additions with near-zero latency/byte cost | Not started |

## Top 3 hypotheses

1. The shortest official-track route now runs through the accepted #549 family or the live #606/#615 variants, not historical #508 alone (Track B).
2. Legal score-first TTT on GEPA still offers the largest upside, but only if it transfers without paying too much throughput or byte tax (Track A).
3. Full GPTQ can be competitive, but only if calibration is cleanly inside the allowed budget; otherwise it risks non-record reclassification (#609 lesson).

## Stop/go rules

- **STOP** any branch where single-seed fails to beat parent by ≥0.001 BPB
- **STOP** any branch where step time increases >5% without compensating BPB gain
- **STOP** any branch where artifact exceeds 15.9 MB after packaging
- **GO** to 3-seed only when single-seed clears promotion threshold
- **GO** to PR packaging immediately when 3-seed mean clears accepted-record territory
