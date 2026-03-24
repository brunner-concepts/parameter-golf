# PR #414 Managed Smoke Run on 1x H100 PCIe

```
hypothesis: The managed PR #414 smoke path can complete end-to-end on 1x H100 PCIe after fixing the FlashAttention bootstrap ref.
parent_branch: repro/pr414
exact_diff: scripts/bootstrap_runpod_env.sh; run_specs/repro_pr414_smoke.json; run_specs/repro_pr414_full.json
train_step_time_ms: 300.97
eval_time_s: 470.072
artifact_bytes: 5152778
pre_quant_bpb: 1.9565
post_quant_bpb: 5.60109723
legality_risk: none
recommendation: revise
notes: Managed smoke completed successfully on March 24, 2026 after the FlashAttention ref was repinned. Operationally this is a success: the watchdog, mirror, dashboard, dataset path, tokenizer, training loop, EMA path, and artifact packaging all completed on cheap compute. Scientifically it is still non-promotional: this was a 120s, 1-shard, 1x-GPU smoke run, so the observed BPBs are not comparable to the published 1.1233 frontier target. The dominant new finding is economic, not modeling: bootstrap_env alone took 7709.693s because FlashAttention compilation consumed the vast majority of wallclock. Before any 8x reproduction, this startup tax must be amortized via a reusable wheel, warmed image, or equivalent artifact transfer.
```
