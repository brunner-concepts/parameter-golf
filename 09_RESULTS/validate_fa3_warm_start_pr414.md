# FlashAttention Warm-Start Validation for PR #414

```
hypothesis: The cached FlashAttention payload can restore cleanly on a fresh pod, eliminating the expensive source-build tax before any serious PR #414 reproduction spend.
parent_branch: repro/pr414
exact_diff: scripts/bootstrap_runpod_env.sh; run_specs/validate_fa3_warm_start_pr414.json; scripts/launch_runpod_managed_run.py
train_step_time_ms: n/a
eval_time_s: n/a
artifact_bytes: n/a
pre_quant_bpb: n/a
post_quant_bpb: n/a
legality_risk: none
recommendation: promote
notes: The managed warm-start validation completed successfully on March 25, 2026. The single bootstrap phase finished in 345.076s with `flash_attn_interface already available`, confirming that the exported cache restored correctly and avoided the prior source-build path that took 7709.693s in the managed smoke. This run was infrastructure-only: no model training, eval, or artifact packaging occurred. The pod remained up after terminal completion and was stopped on March 27, 2026 to stop idle spend.
```
