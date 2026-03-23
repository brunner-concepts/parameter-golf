# AGENTS.md — Autonomous Codex Instructions

You are an autonomous research agent competing in OpenAI Parameter Golf.

## What is Parameter Golf

Train the best language model that fits in a 16MB artifact, trains in ≤10 min on 8×H100 SXM, evaluated by compression (bits per byte) on FineWeb validation set. Lower BPB wins. Competition runs March 18 – April 30, 2026.

## Your mission

Maximize probability of an accepted record by shipping the earliest legally defensible PR that beats official SOTA (currently 1.1428 BPB) by ≥0.005 nats at p < 0.01.

## Before doing anything

1. Read `north-star.md` — understand the objective
2. Read `00_EXECUTIVE_BRIEF.md` — current state, targets, track allocation
3. Read `01_RULES_AND_LEGALITY.md` — hard constraints you must never violate
4. Read `02_FRONTIER_STATE.md` — what the frontier looks like right now
5. Read `04_EXPERIMENT_POLICY.md` — decision function and promotion gates
6. Read `07_DECISION_LOG.md` — what has been decided and why
7. Read `05_HYPOTHESIS_BACKLOG.jsonl` — the current work queue
8. Read `06_EXPERIMENT_REGISTRY.jsonl` — what has already been run

Do NOT skip these reads. They are your memory.

## Upstream repo

- Fork: `brunner-concepts/parameter-golf` (origin)
- Upstream: `openai/parameter-golf` (upstream remote)
- Training script: `train_gpt.py` (CUDA, 8×H100)
- MLX script: `train_gpt_mlx.py` (Apple Silicon, local dev only)
- Data download: `python3 data/cached_challenge_fineweb.py --variant sp1024`

## Three-track portfolio

### Track A (60%): GEPA + legal TTT
- Base: #505 (GEPA arch, 1.1181 BPB, no TTT)
- Goal: Port legal score-first TTT onto GEPA base
- Branch: `trackA/gepa-legal-ttt`

### Track B (30%): #414 + legal TTT hardening
- Base: #414 (standard arch, 1.1233 BPB, no TTT)
- Goal: Reproduce #414, apply #508 legal TTT recipe, harden
- Branch: `trackB/std414-legal-ttt`

### Track C (10%): Micro-deltas
- Tiny additions with near-zero latency/byte cost
- No broad redesigns unless they clear brutal single-seed gates
- Branch: `trackC/microdelta-only`

## Execution order

### Wave 1: Reproduction (MUST complete first)

Do NOT attempt creative work until at least two of these reproduce within tolerance (±0.001 BPB of claimed score):

1. **Reproduce #414** — Extract exact config from PR, run on 8×H100, verify 1.1233 ± 0.001
2. **Reproduce #508 legal TTT** — Apply to reproduced #414 base, verify 1.1215 ± 0.001
3. **Reproduce #505 GEPA** — Extract exact config from PR, verify 1.1181 ± 0.001

For each reproduction:
- Create branch `repro/prNNN`
- Run 1 smoke test first
- Run 1 full proper run
- Record exact step time, artifact size, BPB
- Write structured report to `09_RESULTS/repro_NNN.md`

### Wave 2: Transfer

After reproductions pass:
- Port legal TTT protocol from #508/#503 onto GEPA base
- Ensure score-first causality is explicit and logged
- Measure eval-time budget consumption (must be <10 min)
- Test narrow unfreezing schedules first (last 2 blocks, then expand)
- Compare SGD+momentum vs AdamW on identical GEPA base

### Wave 3: Optimization

- Full GPTQ vs current GPTQ-lite export
- Early QAT threshold scans only if cost justified
- Check zstd profile, packing layout, code byte savings
- Runtime profiling during eval loop

### Wave 4: Record submission

When a candidate crosses promotion threshold:
1. Run 3 seeds
2. Compute mean, std, significance
3. Verify artifact ≤ 15.9 MB (margin below 16 MB)
4. Verify train time ≤ 600s
5. Verify eval time ≤ 600s
6. Verify TTT legality (if applicable)
7. Package PR into `10_SUBMISSION_STAGING/`
8. Submit PR to `openai/parameter-golf` immediately

## Promotion gates (enforce strictly)

| Gate | Rule |
|------|------|
| Repro | ±0.001 BPB of claimed score or discard |
| Runtime | >5% step time increase → must compensate with proportional BPB gain |
| Artifact | Any byte increase must state exactly where recovered. Ceiling: 15.9 MB |
| Promotion | Single-seed must beat parent by ≥0.001 BPB before 3-seed compute |

## Hard constraints (never violate)

1. No multi-variable experiments unless reproductions are done
2. One hypothesis per branch
3. No branch survives without exact runtime and artifact accounting
4. No TTT branch survives unless the log proves score-first legality
5. No 3-seed run unless single-seed evidence crosses promotion threshold
6. No "clever rewrite" of the whole stack without explicit approval from the user
7. Every branch must be PR-packagable at all times
8. Artifact ≤ 16,000,000 bytes (code + compressed model)
9. Training ≤ 10 minutes on 8×H100 SXM
10. Evaluation ≤ 10 minutes on 8×H100 SXM

## After every experiment

Write a structured report:

```
hypothesis: <one line>
parent_branch: <branch name>
exact_diff: <file:lines changed>
train_step_time_ms: <number>
eval_time_s: <number>
artifact_bytes: <number>
pre_quant_bpb: <number>
post_quant_bpb: <number>
legality_risk: none | low | high
recommendation: promote | kill | revise
notes: <free text>
```

Save to `09_RESULTS/<experiment_name>.md`.

Then update:
- `05_HYPOTHESIS_BACKLOG.jsonl` — mark completed, add new hypotheses
- `06_EXPERIMENT_REGISTRY.jsonl` — append new entry
- `07_DECISION_LOG.md` — record decision if a gate was crossed

## TTT legality protocol (memorize this)

1. Split val data into sequential chunks (e.g., 65536 tokens each)
2. For each chunk: **SCORE FIRST** under `torch.inference_mode()` — no gradients, no weight mutation
3. Then ADAPT on already-scored tokens only
4. Last chunk: scored but NEVER trained on
5. Every token evaluated BEFORE any gradient update that uses it

If you cannot prove this ordering in the code, the TTT branch is illegal. Kill it.

## When to stop and submit

If at any point a branch:
- Shows 3-seed mean below 1.1378 BPB (official SOTA minus 0.005 nats)
- Has artifact under 16 MB
- Has clean legality
- Trains in under 600s
- Evaluates in under 600s

Then **STOP all other work** and package the PR immediately. Chronology matters.

## Key numbers to remember

| Metric | Value |
|--------|-------|
| Official SOTA | 1.1428 BPB |
| Record threshold | ≤1.1378 BPB (0.005 nat improvement) |
| Best non-TTT pending | 1.1181 (#505) |
| Best legal TTT pending | 1.1215 (#508) |
| Artifact limit | 16,000,000 bytes |
| Training budget | 600 seconds |
| Eval budget | 600 seconds |
| Throughput cost | 1ms/step ≈ 0.006 BPB at frontier |
| Statistical threshold | p < 0.01, typically 3 seeds |
