hypothesis: The PR #868 repro overshot the published score because the evaluation surface drifted, most likely through an unpinned challenge-data snapshot, not because the base model or top-level config materially differed.
parent_branch: repro/pr868
exact_diff: synced upstream PR #868 seed logs via `scripts/sync_repro_targets.py`; patched `scripts/mirror_runpod_watchdog.py` so terminal-complete runs are not misclassified as infra exits after teardown; patched `scripts/prepare_parameter_golf_data.sh` to archive the challenge manifest hash and shard inventory into future run artifacts
train_step_time_ms: 85.80 (ours) vs 86.33 (upstream seed 1337)
eval_time_s: 495.326 (ours) vs 446.935 (upstream seed 1337)
artifact_bytes: 13416133 (ours) vs 13422021 (upstream seed 1337)
pre_quant_bpb: 1.1408 (ours) vs 1.1412 (upstream seed 1337 diagnostic)
post_quant_bpb: 0.09749802 (ours exact n-gram) vs 0.11819909 (upstream seed 1337 exact n-gram)
legality_risk: low
recommendation: revise
notes: |
  Audit scope:
  - Compare the synced upstream PR #868 artifacts (`README.md`, `submission.json`, `train_gpt.py`, and the newly synced `train_seed*.log` files) against the generated full repro spec and the mirrored terminal output from `repro_pr868_full`.
  - Determine whether the `0.09749802` result is explained by an obvious config mismatch, a model-path mismatch, or a deeper evaluation/data divergence.

  What matches cleanly:
  - Top-level env parity is present. The generated spec sets the same key knobs the PR documents:
    - `MODEL_PRESET=frontier_lean`
    - `RUN_PROFILE=full_8gpu_600s`
    - `TTT_ENABLED=0`
    - `QAT_MODE=off`
    - `NGRAM_EVAL_ENABLED=1`
    - `NGRAM_EVAL_MAX_ORDER=12`
    - `NGRAM_TWO_PASS_ENABLED=1`
    - `NGRAM_TWO_PASS_RESCORE_CHUNKS=72`
    - `NGRAM_BUDGETED_TUNER=1`
    - `NGRAM_BUDGET_TARGET_SECONDS=580`
    - `NGRAM_BUDGET_SAFETY_SECONDS=8`
  - The executed file path is the synced upstream payload itself via `scripts/run_upstream_record.sh`, which `cd`s into `third_party/upstream_prs/pr868` and runs `python -m torch.distributed.run train_gpt.py`.
  - Base-model behavior is very close to the upstream seed-1337 log:
    - final train checkpoint: `step:6993` vs `step:6951`
    - step time: `85.80ms` vs `86.33ms`
    - diagnostic post-average eval: `1.1408` vs `1.1412`
    - quantized roundtrip exact: `1.15836153` vs `1.15941374`
    - artifact size: `13,416,133` vs `13,422,021`

  Where the divergence actually is:
  - The mismatch is concentrated in the score-first n-gram evaluator, not the base model.
  - Our completed run reports:
    - `ngram_pass1_total bpb: 0.2844`
    - `ngram_budgeted_tuner pass1_s:326.0 avg_chunk_s:5.175 available_s:246.0 requested:72 tuned:47`
    - `ngram_pass2: rescoring first 47 chunks with full cache (63 chunks)...`
    - `final_ngram_exact val_bpb: 0.09749802`
  - The synced upstream seed logs consistently report:
    - `ngram_pass1_total bpb: ~0.2860-0.2862`
    - `ngram_budgeted_tuner ... requested:72 tuned:72`
    - `ngram_pass2: rescoring first 72 chunks with full cache (237 chunks)...`
    - `final_ngram_exact val_bpb: 0.11819909 / 0.11813478 / 0.11811002`
  - Since `train_gpt.py` computes `n_chunks` directly from `total_tokens` and `NGRAM_EVAL_CHUNK_TOKENS`, the `63` vs `237` discrepancy means the evaluator is seeing a materially smaller or differently segmented validation surface in our repro.

  Strongest current diagnosis:
  - The most likely root cause is evaluation-surface drift, probably from challenge-data snapshot drift or manifest drift rather than model/config drift.
  - Evidence:
    1. The data downloader `data/cached_challenge_fineweb.py` pulls from the Hugging Face dataset repo head (`willdepueoai/parameter-golf`) and current `manifest.json`; it is not pinned to a dataset snapshot digest or PR-specific data manifest.
    2. The upstream PR payload does not vendor a dataset manifest snapshot; it assumes the challenge data reachable at run time.
    3. Base-model metrics are nearly identical, but the n-gram evaluator sees far fewer chunks and therefore a different budget/tuning regime.

  What this does and does not prove:
  - This audit explains why the current `0.09749802` should not be treated as a submission-ready reproduction.
  - It does not yet prove the exact byte-for-byte data mismatch on the remote pod, because the March 28 run did not capture the downloaded manifest and validation shard inventory into the artifact bundle.
  - Therefore the result is now best classified as: `unresolved, with a strong leading diagnosis`.

  Operational fixes completed during the audit:
  - `scripts/sync_repro_targets.py` now syncs the upstream `train_seed1337.log`, `train_seed42.log`, and `train_seed2025.log` files for PR #868 so future audits do not rely only on README/submission claims.
  - `scripts/mirror_runpod_watchdog.py` now falls back to the last mirrored local snapshot when a pod exits, so completed runs are not rewritten as `infra_provider_exit` after teardown.
  - `scripts/prepare_parameter_golf_data.sh` now writes `artifacts/challenge_data/challenge_data_snapshot.json` plus the downloaded `manifest.json` into `RUN_DIR` so the next cache repro preserves the exact data-surface evidence needed for parity checks.

  Next exact step:
  1. Add explicit capture of the challenge-data manifest, validation shard count, and downloaded dataset paths into the run-control artifact set for all future cache repros.
  2. Pin or snapshot the exact challenge-data manifest used for the next `#868` rerun.
  3. Only after eval-surface parity is proven should another expensive `#868` confirmation run or a submission decision happen.
