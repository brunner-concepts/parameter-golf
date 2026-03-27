# Frontier State

Last updated: 2026-03-27

## Official leaderboard

Source: upstream [README](https://github.com/openai/parameter-golf/blob/main/README.md) and live tracker issue #140 as of March 27, 2026.

| Rank | BPB | Author | Record / PR lineage |
|------|-----|--------|---------------------|
| 1 | **1.1194** | PR #549 | Accepted official record: LeakyReLU² + Legal Score-First TTT + Parallel Muon on the PR #414 stack |
| 2 | 1.1228 | signalrush | Accepted record package based on the PR #414 direction |
| 3 | 1.1248 | jfprincz | Accepted record package based on the PR #287 / #315 family |

## Live record-eligible frontier

Source: Issue #140 live commentary plus current PR heads on March 26-27, 2026.

| PR | BPB | Type | Description | Interpretation |
|----|-----|------|-------------|----------------|
| #913 | **0.0887** | Eval cache | Minimal 2-layer GPT + online n-gram / phrase cache with adaptive blending | **Current best record-eligible route; the cache does nearly all the work.** |
| #870 | **0.0935** | Eval cache, aggressive | Full-rescore n-gram cache over all tokens | Extremely strong, but explicitly more aggressive on legality because of full-cache rescore / self-inclusion. |
| #921 | **0.0939** | Eval cache | Order-13 full-rescore n-gram + 11L int6 GPTQ | Confirms the cache frontier is not a single one-off result. |
| #888 | **0.0942** | Eval cache | Fast full-rescore n-gram | Strong record-eligible cache result; more evidence the cache regime is dominant. |
| #907 | **0.0960** | Eval cache | Two-pass order-12 shared n-gram tables | Strong additional cache confirmation. |
| #868 | **0.1181** | Eval cache, conservative | Budgeted two-pass n-gram backoff | Important stepping-stone reproduction target because it is closer to a conservative legality posture. |
| #606 | **1.1162** | Legal TTT | Int5 GPTQ + Soft-Round QAT + legal cosine AdamW TTT | Still the strongest live legal-TTT neural result, but now far behind the cache frontier. |
| #634 | **1.1178** | Non-TTT | XSA-all + Full GPTQ (budget-legal) + Parallel Muon + Selective Pruning | Strong pure-neural result, but no longer near record contention. |
| #505 | **1.1181** | Non-TTT | GEPA arch: SwiGLU + VE128 + U-Net Skip Gates, 11L, seq2048 | Still the strongest simple GEPA base, but now strategically secondary. |
| #414 | **1.1233** | Non-TTT | 11L EMA + GPTQ-lite + warmdown3500 + QAT@0.15 | Reproduction anchor only; not a winning endpoint. |
| #609 | **1.1154** | Non-record | XSA-all + Full GPTQ + Selective Pruning | Reminder that lower BPB alone is insufficient without clean budget accounting. |

## Strategic interpretation

1. **The competition has structurally changed.**
   In the live record-eligible frontier, the dominant technique is no longer neural architecture or legal TTT. It is backward-looking eval-time cache engineering. Issue #140 reports `0.0887` pending on March 26-27, roughly a full BPB below the official leaderboard.

2. **Pure-neural `#414` reproduction is no longer the shortest record path.**
   `#414` remains useful for control-plane confidence and as historical lineage for the accepted leaderboard, but it is now badly behind the live frontier. Running the full repro may still be useful as an engineering anchor; it is not the highest-EV route to an accepted record.

3. **Legality risk moved from TTT ordering to cache interpretation.**
   The important question is no longer only “score-first TTT or not.” It is also whether aggressive two-pass / full-rescore cache methods are interpreted as legal when later rescoring uses a cache built from all previously scored tokens. Conservative online cache paths therefore matter strategically, not just academically.

4. **Artifact and eval engineering now dominate.**
   `#913` claims `622 KB` artifact size, `122s` train time, and `403s` eval time. That means the artifact budget is no longer tight on the leading path; the real bottleneck is implementing a fast, legal cache mixer and packaging it cleanly.

5. **Our own blocker has changed.**
   The FlashAttention warm-start gate succeeded on March 25, 2026 (`345.076s` bootstrap vs the prior `7709.693s`). Infrastructure is no longer the main excuse for delay. The remaining gap is strategic: the repo is still pointed at a lane that is no longer closest to a win.

## Reproduction notes

- **#913**: Minimal integration path from the baseline. PR text claims only `36` added lines to `train_gpt.py` plus one new `ngram_cache.py`, `622 KB` artifact, `122s` train, and `403s` eval. This is the cleanest current reproduction target.
- **#870**: Stronger than `#868`, but explicitly flags its own full-rescore / self-inclusion aggressiveness. Treat as a powerful idea source, not the safest first submission path.
- **#868**: Useful stepping stone because it is closer to a conservative legality interpretation while already clearing the official accepted record by a huge margin.
- **#414**: Historical anchor only. If reproduced, use it to validate the control plane and lineage understanding, not as the main path to a win.
- **#609**: Still the cautionary budget-accounting case for any GPTQ-heavy path.

## Key implementation components to watch

From **#913 / cache frontier**:
- Tiny baseline model is sufficient; the cache dominates compression
- Online backward-looking n-gram and phrase caches
- Adaptive blending between model probs, n-gram stats, and phrase matches
- Strict score-first cache updates from already-scored tokens only
- Eval engineering matters more than training architecture

From **#868 conservative stepping stone**:
- Two-pass backoff cache
- More conservative legality posture than full-rescore
- Useful target if the repo wants the safest first cache reproduction

From **legacy neural frontier**:
- `#549/#606/#634/#505` are still worth understanding for fallback and hybrid ideas
- But they are no longer the direct route to first-priority record contention

## Economics

At ~86ms/step, each 1ms of per-step overhead costs ~0.006 BPB near the frontier. This still dominates most idea quality arguments.

From the current live frontier:
- training is cheap,
- eval is the battleground,
- and the winning path can fit in well under 1 MB.

From our own latest infra work:
- the model-side smoke path works,
- FlashAttention warm-start has been validated,
- and further pure infrastructure work should now be justified only if it directly accelerates cache-route reproduction or packaging.
