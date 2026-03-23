# PR #414 Smoke Run

```
hypothesis: The PR #414 stack can bootstrap cleanly on RunPod and complete a 1xH100 smoke run before we spend 8xH100 SXM compute.
parent_branch: repro/pr414
exact_diff: none in model code; operational bootstrap only on upstream PR #414 path
train_step_time_ms: 223.01
eval_time_s: 57.171
artifact_bytes: 5498663
pre_quant_bpb: 1.7547
post_quant_bpb: 6.13210912
legality_risk: none
recommendation: revise
notes: Smoke run completed on March 23, 2026 on 1x H100 SXM after one-time FlashAttention-3 bootstrap. This was a 120s, 1-shard operational validation run, not a score-valid reproduction. Operational signals are good: dataset path, tokenizer, training loop, EMA, evaluation, and artifact packaging all completed. Performance signals are not promotion-worthy: the shortened run produced val_bpb 1.7547 at step 539 and the final int6 roundtrip collapsed to 6.1321 BPB, so this run is not publishable and says nothing useful about frontier competitiveness. Use it as infra proof only, then move to a managed full 8x repro with durable logging.
```
