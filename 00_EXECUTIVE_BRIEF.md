# Executive Brief

## Goal

Ship the earliest legally defensible PR that is accepted as the new official record in OpenAI Parameter Golf.

## Current target to beat

Official SOTA: **1.1428 BPB** (thwu1, PR #180)
Best pending non-TTT: **1.1181 BPB** (#505, GEPA arch, 3-seed)
Best pending legal TTT: **1.1215 BPB** (#508, GPTQ + Legal TTT, 3-seed)

To land an accepted record, the submission must beat the official SOTA by ≥0.005 nats at p < 0.01.

## Track allocation

| Track | Allocation | Target | Status |
|-------|-----------|--------|--------|
| **A: GEPA + legal TTT** | 60% | Port legal score-first TTT onto #505 GEPA base | Not started |
| **B: #414 + legal TTT** | 30% | Reproduce #414, harden #508 legal TTT | Not started |
| **C: Micro-deltas** | 10% | Tiny additions with near-zero latency/byte cost | Not started |

## Top 3 hypotheses

1. Legal score-first TTT on GEPA base will beat 1.1181 by at least 0.002 (Track A)
2. GPTQ + Early QAT improvements can further compress #414-family quant tax (Track B)
3. BigramHash bucket scaling or VE dim tuning may yield micro-delta on any base (Track C)

## Stop/go rules

- **STOP** any branch where single-seed fails to beat parent by ≥0.001 BPB
- **STOP** any branch where step time increases >5% without compensating BPB gain
- **STOP** any branch where artifact exceeds 15.9 MB after packaging
- **GO** to 3-seed only when single-seed clears promotion threshold
- **GO** to PR packaging immediately when 3-seed mean clears accepted-record territory
