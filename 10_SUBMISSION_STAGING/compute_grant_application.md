# Compute Grant Application

Tier: **Development grant (~$500 / ~160 compute hours)**

Status: **Ready to submit now.**

---

## Form Fields

### Compute support level

Development grant (~$500 / ~160 compute hours). I have a concrete approach, have experimented, and need more compute.

### Brief description of your approach (max 1,500 characters)

I'm targeting a pure neural submission building on the accepted PR #549 stack (LeakyReLU^2 + legal score-first TTT + Parallel Muon). I have a working RunPod orchestration pipeline that handles pod lifecycle, FlashAttention warm-start, provider-side staging, budget controls, and watchdog execution, validated through multiple full 8x H100 SXM runs.

My earlier work focused on reproducing cache-based approaches in the PR #868 family. Through rigorous parity testing — including a pinned-manifest frozen-surface rerun — I independently identified eval-surface divergence in the n-gram hash evaluation path. Those approaches were subsequently closed by organizers on March 27 after the community confirmed the normalization bug. That work was not wasted: it proved the infrastructure and taught me to stop before submitting an unresolved result.

I am now pivoting to the legal neural frontier with the same battle-tested pipeline. Specific improvements I plan to stack on the #549 base: full Hessian GPTQ with AR self-generated calibration data (reducing the quantization gap), XSA on all 11 layers, BigramHash scaling, and TTT schedule optimization. The infrastructure is technique-agnostic and ready for neural runs today.

The grant would fund: (1) reproduce PR #549 within tolerance, (2) single-variable experiments on each improvement, (3) combine winning deltas, (4) 3-seed validation, (5) submit PR. ~$500 covers approximately 80 full training runs, which is enough for disciplined iteration and a valid submission.

### What have you tried so far? (max 255 characters)

Built full RunPod control plane. Completed 3 full 8xH100 SXM runs. Self-funded $550+$25 credit. Solved FA3 warm-start (7700s->345s). Cache targets closed Mar 27; pivoting to neural frontier with proven infra.

### Link(s) to your PR submission

https://github.com/brunner-concepts/parameter-golf

No competition submission PR yet. Working fork with full operator, control plane, and run history.

---

## Internal notes (do not paste into form)

### Why $500 and not $25 or $1000

- **Not $25:** Already spent $575 of own money and completed multiple full 8x H100 SXM runs. The quick-start tier is for people who have not experimented yet.
- **Not $1000:** No public leaderboard submission. The advanced tier is for people actively competing near the top. Be honest about where we are.
- **$500 is right:** Concrete approach, demonstrated infrastructure, significant self-funded investment, specific plan for compute usage. Matches the development-grant criteria.

### Posture

Strong evidence, disciplined execution, unresolved submission blocker (no valid target yet post-purge), clear next milestone. Not a victory lap. Not speculation.

### Character counts

- Brief description: ~1,446 characters (limit 1,500)
- What tried: ~243 characters (limit 255)

### Evidence to cite if asked follow-up questions

- Self-funded RunPod reloads: $550 (6 Stripe transactions, March 22-28)
- Sponsored RunPod credit: $25
- Full 8x H100 SXM runs completed: 3
- FlashAttention warm-start: 7700s -> 345s
- Provider-side network volume staging: operational in US-GA-2
- Autonomous operator with budget controls, Telegram, repair loop: operational
- Cache eval-surface divergence independently observed before March 27 ruling
- Decision log: 15 major decisions documented in 07_DECISION_LOG.md
- Funding ledger: 11_RUN_CONTROL/funding_ledger.json
