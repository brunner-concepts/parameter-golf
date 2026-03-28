hypothesis: Re-running PR #868 on a pinned challenge-data manifest and frozen dataset revision will collapse the remaining parity gap if the mismatch is coming from a moving eval surface.
parent_branch: repro/pr868
exact_diff: executed via the pinned-manifest generated spec `11_RUN_CONTROL/control_plane/generated_specs/repro_pr868_parity_full.json`; no intended model-code diff versus synced upstream PR #868 payload
train_step_time_ms: 0.02 (ours) vs 0.03 (upstream seed 1337)
eval_time_s: 497.562 (ours) vs 446.935 (upstream seed 1337)
artifact_bytes: 13428797 (ours) vs 13422021 (upstream seed 1337)
pre_quant_bpb: 1.1407 (ours) vs 1.1412 (upstream seed 1337 diagnostic)
post_quant_bpb: 0.09674850 (ours exact n-gram) vs 0.11819909 (upstream seed 1337 exact n-gram)
legality_risk: low
recommendation: kill
notes: |
  Pinned-manifest parity rerun completed at `2026-03-28T21:48:16Z`.

  Key comparison versus the synced upstream seed-1337 log:
  - exact n-gram BPB: `0.09674850` vs `0.11819909`
  - n-gram total chunks: `63` vs `237`
  - tuned chunks: `50` vs `72`
  - n-gram eval time: `497562ms` vs `446935ms`
  - artifact bytes: `13428797` vs `13422021`

  Interpretation:
  - The rerun is operationally successful: the pinned-manifest bootstrap path works and the provider-staged 8x stack remains reproducible.
  - The rerun is still not an understood reproduction. The same core divergence survives the frozen replay, so the original moving-manifest hypothesis is no longer sufficient.
  - Because the exact score delta remains ~`-0.02145059` BPB and the chunk surface remains materially different, this should not be packaged as a competition PR.

  Next exact step:
  1. Stop the current self-funded parity campaign and preserve the evidence.
  2. Update the grant request to describe the now-resolved milestone: full frozen-surface rerun completed, divergence persisted.
  3. Decide between deeper hidden eval-surface forensics and a conservative pivot to the next cache lineage target.
