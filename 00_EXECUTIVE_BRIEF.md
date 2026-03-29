# Executive Brief

## Goal

Ship the earliest legally defensible PR that is accepted as the new official record in OpenAI Parameter Golf.

## Current target to beat

Official SOTA: **1.1194 BPB** (PR #549, merged March 24, 2026)
Likely next merge: **1.1147 BPB** (PR #1019, open, same author as #549)

To land an accepted record, the submission must beat the official SOTA by >=0.005 nats at p < 0.01.
That means the target is approximately **< 1.1160 BPB** (3-seed mean).

## March 27 cache purge

The organizer closed 33+ PRs on March 27 including all cache-based approaches (#868, #913, #933, and the entire n-gram hash family). The ruling: hashed n-gram caches don't normalize over the full token vocabulary, two-pass rescoring breaks causality. The competition has reset to the pure neural frontier.

All previous cache track work is dead. The infrastructure and operational learnings carry forward.

## Track allocation

| Track | Allocation | Target | Status |
|-------|-----------|--------|--------|
| **Neural reproduction** | 100% | Reproduce PR #549, stack legal improvements (GPTQ, XSA-all, BigramHash, TTT tuning), 3-seed validate, submit | Active |

## Top 3 hypotheses

1. The best legal stack combines the #549 base with improvements from #1019 (Full Hessian GPTQ with AR self-gen calibration, XSA on all 11 layers, BigramHash scaling to 3072x112).
2. The infrastructure is validated and technique-agnostic. Retargeting from cache to neural requires spec changes, not a rebuild.
3. The grant application is the single highest-EV immediate action. $500 multiplies available compute by ~6x and makes serious iteration realistic.

## Stop/go rules

- **STOP** any branch where single-seed fails to beat parent by >=0.001 BPB
- **STOP** any branch where step time increases >5% without compensating BPB gain
- **STOP** any branch where artifact exceeds 15.9 MB after packaging
- **STOP** spending on cache-based approaches. They are closed and will not be accepted.
- **GO** to 3-seed only when single-seed clears promotion threshold
- **GO** to PR packaging immediately when 3-seed mean clears accepted-record territory
- **GO** submit grant application immediately
