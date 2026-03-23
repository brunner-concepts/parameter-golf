# Rules and Legality

Source: [openai/parameter-golf README](https://github.com/openai/parameter-golf/blob/main/README.md)

## Hard constraints

| Constraint | Value | Notes |
|-----------|-------|-------|
| Artifact size | ≤ 16,000,000 bytes (decimal, NOT 16 MiB) | Code bytes + compressed model bytes |
| Training time | ≤ 10 minutes on 8×H100 SXM | Wallclock, not GPU-hours |
| Evaluation time | ≤ 10 minutes on 8×H100 SXM | Separate budget from training |
| External downloads | Forbidden during evaluation | Artifact must be fully self-contained |
| Validation data during training | Forbidden | Cannot compress val into artifact ("paid prefix" ruled out) |
| Record improvement | ≥ 0.005 nats over current SOTA | At p < 0.01 significance |
| Statistical evidence | Typically 3 seeds | Must demonstrate significance |

## TTT legality (critical)

Test-time training is allowed **only** on validation tokens that have **already been scored**.

The legal protocol (from #461, #508, #473):

1. Split val data into sequential chunks
2. For each chunk: **score first** under `torch.inference_mode()` (no gradients, no weight mutation)
3. Then **adapt** on already-scored tokens only
4. Last chunk is scored but **never trained on**
5. Every token must be evaluated BEFORE any gradient update that uses it

**Pre-eval TTT is illegal.** Submissions #462 (1.0672) and #518 (1.0814) use pre-eval TTT and are flagged. Do not replicate their TTT approach.

## Submission requirements

A PR that adds a new folder to `/records/track_10min_16mb/` containing:

1. `README.md` — explains submission in detail
2. `submission.json` — name, GitHub ID, val_bpb, metadata
3. Train log — with statistically significant results (3 seeds typical)
4. `train_gpt.py` — must compile and run within the records folder
5. Any other dependencies (requirements.txt if non-standard)

## Chronology warning

Acceptance is chronological by PR creation time. If a branch plausibly clears accepted-record territory, **stop searching and package immediately**. Speed of submission matters.

## Evaluation rules

- Any sequence length allowed
- Sliding window eval allowed (any stride)
- No training data access during eval
- No network calls during eval
- All code counted in artifact size
