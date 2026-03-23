# Frontier State

Last updated: 2026-03-23

## Official leaderboard

| Rank | BPB | Author | PR |
|------|-----|--------|----|
| 1 | 1.1428 | thwu1 | #180 |
| 2 | 1.1458 | Raahil Shah | #162 |
| 3 | 1.1502 | aruniyer | #86 |

## Live tracker — key pending PRs

Source: Issue #140 (live AI commentary)

| PR | BPB | Type | Description | Interpretation |
|----|-----|------|-------------|----------------|
| #505 | **1.1181** | Non-TTT | GEPA arch: SwiGLU + VE128 + U-Net Skip Gates, 11L, seq2048 | **Strongest non-TTT base. Track A parent.** |
| #508 | **1.1215** | Legal TTT | GPTQ + Early QAT + Legal score-first TTT on #414 base | **Best validated legal TTT. Track B target.** |
| #503 | **1.1218** | Legal TTT | 11L XSA11 + AdamW TTT, score-first, last 2 blocks unfrozen | Legal AdamW TTT variant. Alternative TTT recipe. |
| #473 | **1.1220** | Legal TTT | SGD+momentum TTT on #414 base, parameter banking | Legal SGD TTT variant. Parallel Muon optimizer. |
| #414 | **1.1233** | Non-TTT | 11L EMA + GPTQ-lite + warmdown3500 + QAT@0.15 | **Strongest mature standard stack. Track B parent.** |
| #462 | 1.0672 | ⚠️ Pre-eval TTT | GEPA + AdamW TTT | Illegal pre-eval. Do NOT replicate TTT approach. |
| #518 | 1.0814 | ⚠️ Pre-eval TTT | LeakyReLU² + Cosine TTT | Illegal pre-eval. Do NOT replicate TTT approach. |
| #375 | N/A | Negative results | 13 techniques tested, most regressed | **Throughput losses are ruinous near frontier.** |

## Reproduction notes from exact PR heads

- **#414**: PR title claims the 3-seed mean (`1.1233`), but `submission.json` packages the best seed (`1.12278022`). Reproduction tolerance should be checked against the PR claim, not only the packaged seed.
- **#505**: PR head contains only `README.md` and `train_gpt.py`. There is no `submission.json` or train log in the PR files, so reproduction must use the README claim plus code defaults unless upstream adds more artifacts.
- **#508**: PR title claims the 3-seed mean (`1.1215`), while `submission.json` records both the best seed (`1.12059684`) and the mean (`1.12150756`). Use the mean for promotion comparisons and the best seed for packaging parity.

## Key architectural components (current frontier)

From #505 (GEPA):
- SwiGLU FFN with Star-ReLU (relu² + affine), hidden=1792
- U-Net Skip Gates: 5 encoder + 6 decoder with learned gating
- XSA4 (Extended Self-Attention in last 4 layers)
- Value Embeddings (VE128): 128-dim shared, per-layer scales on layers 9-10
- BigramHash: 8192 buckets, 128-dim
- EMA decay=0.997, Partial RoPE 16 dims
- LN Scale, Late QAT@0.15, Int6 + GPTQ-lite + zstd-22
- Sequence length 2048 (key: +0.008 BPB over seq1024)

From #414 (standard):
- 11L, 512d, 8H/4KV, MLP 3× (relu²)
- U-Net skips, XSA4, Partial RoPE 16/64
- LN Scale, VE128, SmearGate, BigramHash(2048)
- EMA(0.997), Tight SWA, Muon WD=0.04
- GPTQ-lite (5-percentile per-row optimal clip), int6+zstd-22
- Late QAT@0.15, ~82-89ms/step, ~7100 steps in 600s

From #508 (legal TTT recipe):
- GPTQ quantization: 256-sample calibration, column reordering, block-128 Cholesky error compensation
- Early QAT threshold 0.5 (3× more QAT steps)
- Score-first TTT: EMA scoring (decay=0.995), cosine LR over 200 chunks
- Embedding freeze during TTT, SGD+momentum 0.9, 3 epochs/chunk, grad clip 1.0
- Quant tax reduced from 0.0082 to 0.0058 BPB (32% reduction)

## Economics (#375 meta-insight)

At 86ms/step, each 1ms of per-step overhead costs ~0.006 BPB. Most frontier ideas fail this throughput test. EMA > SWA by 0.003 BPB. Weight decay controls compressed artifact size (~1.5-2MB per 0.01 WD). Batch 786K > 524K by 0.004 BPB. FA3 Hopper gives 15-20% more steps at same wallclock.
