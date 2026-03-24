# Frontier State

Last updated: 2026-03-24

## Official leaderboard

Source: upstream [README](https://github.com/openai/parameter-golf/blob/main/README.md) as of March 24, 2026.

| Rank | BPB | Author | Record / PR lineage |
|------|-----|--------|---------------------|
| 1 | **1.1194** | abaybektursun | Accepted official record on PR #549: LeakyReLU² + Legal Score-First TTT + Parallel Muon on the PR #414 stack |
| 2 | 1.1228 | signalrush | Accepted record package based on the PR #414 direction |
| 3 | 1.1248 | jfprincz | Accepted record package based on the PR #287 / #315 family |

## Live validated frontier

Source: Issue #140 live commentary plus current PR heads on March 24, 2026.

| PR | BPB | Type | Description | Interpretation |
|----|-----|------|-------------|----------------|
| #606 | **1.1162** | Legal TTT | Int5 GPTQ + Soft-Round QAT + legal cosine AdamW TTT | **Best live legal-TTT frontier currently visible.** |
| #615 | **1.1169** | Legal TTT | Residual Input Mixing + mixed int6 GPTQ + grouped TTT + MLP 3.5x | Strong live legal-TTT alternative; shows architecture changes can still matter. |
| #634 | **1.1171** | Non-TTT | XSA-all + Full GPTQ + Parallel Muon + Selective Pruning | Strongest live non-TTT frontier currently visible. |
| #626 | **1.1180** | Non-TTT | Full GPTQ + LeakyReLU² + Parallel Muon | Independent confirmation that the accepted #549 family has strong non-TTT legs too. |
| #505 | **1.1181** | Non-TTT | GEPA arch: SwiGLU + VE128 + U-Net Skip Gates, 11L, seq2048 | **Still the strongest simple GEPA base and Track A parent.** |
| #578 | **1.1215** | Legal TTT | Full GPTQ + Early QAT + Legal TTT on the #414 stack | Historically important, but now superseded by accepted #549 and newer live runs. |
| #414 | **1.1233** | Non-TTT | 11L EMA + GPTQ-lite + warmdown3500 + QAT@0.15 | **Still the right reproduction anchor, but no longer a plausible winning endpoint.** |
| #609 | **1.1154** | Non-record | XSA-all + Full GPTQ + Selective Pruning | **Important warning:** reclassified non-record because GPTQ calibration was outside the allowed training budget. |
| #375 | N/A | Negative results | 13 techniques tested, most regressed | Throughput losses are still ruinous near the frontier. |

## Strategic interpretation

1. **Legal score-first TTT is now officially accepted.**
   PR #549 merged on March 24, 2026 and now tops the official README leaderboard at `1.1194`. This materially lowers legality uncertainty for the #414-family TTT path.

2. **The old Track B target is stale.**
   Reproducing `#414` is still useful as a clean delta anchor, but `#508` is no longer the frontier target. The real Track B competition is now `#549`, `#606`, and `#615`.

3. **Full GPTQ is promising but governance-sensitive.**
   The live tracker explicitly reclassified `#609` as non-record because calibration happened outside the training budget. Any Full GPTQ path must account for calibration cleanly inside the allowed budget.

4. **GEPA still matters, but the accepted bar moved below it.**
   `#505` at `1.1181` remains an excellent base, but the official accepted record is already `1.1194`. GEPA without a new transfer or systems edge is no longer enough by itself.

5. **Chronology pressure increased.**
   The frontier between `1.116x` and `1.118x` is now crowded with multiple open PRs. Any future record attempt should target a score materially below `1.1194`, not just barely below the previous `1.1428` era threshold.

## Reproduction notes

- **#549**: Officially merged and accepted. This is now the authoritative proof that legal score-first TTT on the `#414` family is record-eligible.
- **#414**: PR title claims the 3-seed mean (`1.1233`), but `submission.json` packages the best seed (`1.12278022`). Reproduction tolerance should be checked against the PR claim, not only the packaged seed.
- **#505**: PR head still contains only `README.md` and `train_gpt.py`. There is no `submission.json` or train log in the PR files, so reproduction must use the README claim plus code defaults unless upstream adds more artifacts.
- **#578**: Use it as a historical recipe source, not as the current frontier target.
- **#609**: Treat as a cautionary case for calibration accounting, not as a direct record target.

## Key architectural components to watch

From **#549 accepted stack**:
- LeakyReLU(0.5)² activation on the `#414` family
- Legal score-first TTT
- Parallel Muon
- Accepted official record at `1.1194`

From **#505 (GEPA)**:
- SwiGLU FFN with Star-ReLU (relu² + affine), hidden=1792
- U-Net Skip Gates: 5 encoder + 6 decoder with learned gating
- XSA4 in the deepest layers
- VE128 with per-layer scales
- BigramHash 8192, seq2048

From **#414 family**:
- 11L, 512d, 8H/4KV, MLP 3× (relu² baseline)
- U-Net skips, XSA4, Partial RoPE 16/64
- LN Scale, VE128, SmearGate, BigramHash(2048)
- EMA(0.997), Tight SWA, Late QAT, FA3

## Economics

At ~86ms/step, each 1ms of per-step overhead costs ~0.006 BPB near the frontier. This still dominates most idea quality arguments.

From our own latest managed smoke:
- the model-side smoke path works,
- but rebuilding FlashAttention from source on every pod is economically unacceptable.

Warm-starting FA3 is now part of the critical path to any serious 8x reproduction.
