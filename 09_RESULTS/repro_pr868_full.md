hypothesis: A conservative, score-first two-pass n-gram cache reproduction of PR #868 will produce a record-eligible result on 8x H100 SXM with clean runtime and artifact accounting.
parent_branch: repro/pr868
exact_diff: no intended model-code diff versus synced upstream PR #868 payload; executed via provider-staged shared cache and generated spec `11_RUN_CONTROL/control_plane/generated_specs/repro_pr868_full.json`
train_step_time_ms: 85.80
eval_time_s: 495.326
artifact_bytes: 13416133
pre_quant_bpb: 1.1408
post_quant_bpb: 0.09749802
legality_risk: low
recommendation: revise
notes: |
  Full provider-staged 8x repro completed successfully at `2026-03-28T15:11:12Z`.

  Key terminal metrics from the mirrored summary:
  - wallclock stop: `step:6993/20000 ... train_time:600027ms`
  - diagnostic post-average eval: `val_bpb 1.1408`
  - quantized roundtrip exact: `val_bpb 1.15836153`
  - final score-first n-gram exact: `val_bpb 0.09749802`
  - total submission size: `13,416,133` bytes
  - n-gram eval time: `495.326s`

  Interpretation:
  - Operationally, this is the first successful full 8x provider-staged cache-route repro. The previous Mac-to-pod FlashAttention transport bottleneck is solved.
  - Scientifically, this is **not yet an understood reproduction** of PR #868. The claimed upstream score is `0.11814796`, so this run overshot the claim by ~`0.02065` BPB instead of landing within the project’s ±`0.001` repro tolerance.
  - The training wallclock logged `600.027s`, which is also slightly above the nominal `600s` budget and needs interpretation before any packaging decision.
  - Because the result is materially better than the claim, the correct next step is not auto-promotion. First determine whether the delta comes from upstream drift, evaluation drift, data/order drift, or a different effective configuration than the published claim.

  Immediate follow-up:
  1. Reconcile exact synced PR #868 files and run config against the generated spec used here.
  2. Confirm legality and score-first ordering from the mirrored logs/code path.
  3. Only after understanding the mismatch decide whether to rerun #868, pivot to #913, or inspect #933.
