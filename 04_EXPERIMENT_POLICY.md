# Experiment Policy

## Decision function

```
EV = p(successful accepted record) × magnitude of improvement ÷ time-to-evidence
```

Not beauty. Not novelty. Not "the model likes it."

## Promotion gates

### Gate 1: Repro tolerance
Within a tight band of claimed score (±0.001 BPB) or discarded as "not understood."

### Gate 2: Runtime
If training step-time increases materially (>5%), candidate must pay for it with proportional BPB gain immediately. At 86ms/step, 1ms overhead ≈ 0.006 BPB penalty.

### Gate 3: Artifact
If bytes increase, the agent must explicitly state where they are recovered. No handwaving. Budget ceiling: 15.9 MB with margin.

### Gate 4: Promotion to 3-seed
Single-seed must beat parent by ≥0.001 BPB before 3-seed compute is spent. Additionally:
- Artifact under budget with margin
- No legality issue
- No significant eval-time blowup
- No measurable training instability

## Hard constraints

1. No multi-variable experiments unless reproductions are done
2. One hypothesis per branch
3. No branch survives without exact runtime and artifact accounting
4. No TTT branch survives unless the log proves score-first legality
5. No 3-seed run unless single-seed evidence crosses promotion threshold
6. No "clever rewrite" of the whole stack without explicit CEO approval
7. Every branch must be PR-packagable at all times

## Branch naming

```
trackA/gepa-legal-ttt
trackA/gepa-legal-ttt-adamw
trackB/std414-repro
trackB/std414-legal-ttt
trackC/microdelta-bigramhash-16k
repro/pr414
repro/pr505
repro/pr508
```

## Experiment report template

Every run must produce a structured report in 09_RESULTS/:

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
