# Frontier State

Last updated: 2026-03-29

## March 27 cache purge

On March 27, organizer @valerio-oai closed 33+ PRs after the community (led by @abaybektursun in PR #886 and @Eppie in issue #677) mathematically proved that hashed n-gram eval caches are invalid:

- The hash lookup is conditioned on the target token, so it "looks ahead" and produces an improperly normalized probability.
- Two-pass rescoring scores tokens using a cache built from tokens that appear after them, breaking causality.
- A bucket sweep proved the "improvement" tracks collision density, not prediction quality.

**New rule:** At position `t`, the predictive distribution must depend only on the artifact and the strict prefix `x_1, ..., x_{t-1}`. Full normalization over the entire token alphabet required. No two-pass rescoring.

**Closed targets from this project:** #868, #913, #933 — all dead.
**New PR threshold:** Organizer only reviewing PRs > #988.

## Official leaderboard

Source: upstream README and issue #140 as of March 29, 2026.

| Rank | BPB | Author | Record / PR lineage |
|------|-----|--------|---------------------|
| 1 | **1.1194** | abaybektursun | PR #549: LeakyReLU(0.5)^2 + Legal Score-First TTT + Parallel Muon |
| 2 | 1.1228 | signalrush | PR #414: 11L EMA + GPTQ-lite + warmdown3500 + QAT@0.15 |
| 3 | 1.1248 | jfprincz | PR #315 family |

## Live post-purge frontier (pure neural only)

| PR | BPB | Seeds | Technique | Status |
|----|-----|-------|-----------|--------|
| #1019 | **1.1147** | 3 | AR self-gen Full Hessian GPTQ + XSA-all + BigramHash 3072x112, NO TTT | Open, likely next merge |
| #999 | **1.1179** | 3 | Muon TTT + entropy-adaptive epoch selection (2/3/4 per chunk) | Open, marginal delta |
| #1004 | **1.1182** | 1 | 33.6M params (d=576, MLP 3.5x), int5 GPTQ, XSA-all, BigramHash(8192) | Open, needs 2 more seeds |
| #1006 | **1.1085** | 1 | JEPA auxiliary loss + AdamW pre-quant TTT + Full Hessian GPTQ + XSA-all | Open, single seed only |
| #838 | **1.1215** | 3 | Pure neural, legal score-first TTT, EMA pre-quant 1.1160 | Open, not competitive |

## Competitive threshold

- Current merged SOTA: **1.1194 BPB** (~1.89002 nats)
- Merge threshold: must beat by > 0.005 nats -> target < **~1.1160 BPB**
- If PR #1019 merges first: target moves to < **~1.1097 BPB**

## Legal techniques (proven, high-impact)

| Technique | Approximate gain | Source |
|-----------|-----------------|--------|
| Legal score-first TTT | ~0.0025 BPB | #549 |
| LeakyReLU(0.5)^2 (or slope 0.9) | ~0.003 BPB | #549, community experiments |
| Full Hessian GPTQ with AR self-gen calibration | ~0.006 BPB (quant gap reduction) | #1019 |
| XSA on all 11 layers (not just last 4) | free improvement | #1019 |
| BigramHash scaling (1536 -> 3072x112) | small gain | #1019 |
| Parallel Muon optimizer | part of baseline | #549 |
| EMA(0.997) + SWA + Late QAT | part of baseline | #414/#549 |

## Techniques ruled invalid

- Hashed n-gram eval caches (normalization bug)
- Two-pass rescoring (causality violation)
- Multi-epoch TTT with final-epoch scoring
- Eval-time GPTQ calibration on training data
- Oracle/hindsight selection (min across passes)

## Strategic interpretation

1. **The competition is back to pure neural.** The cache wave (March 25-27) is over. The leaderboard is intact because all cache PRs were invalidated.
2. **The gap is small but real.** #549 (1.1194) to #1019 (1.1147) is only 0.0047 BPB. Improvements are measured in thousandths.
3. **The key innovations in #1019 vs #549:** Dropped TTT entirely. Added Full Hessian GPTQ with self-generated calibration data (model generates its own calibration sequences). Added XSA on all 11 layers. Scaled BigramHash to 3072x112.
4. **Combining TTT from #549 with GPTQ/XSA from #1019** is the obvious next experiment. Neither PR does both.
5. **Our infrastructure carries over.** The operator stack is technique-agnostic. Retargeting to neural requires only spec changes.
