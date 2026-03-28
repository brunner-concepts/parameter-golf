# Compute Grant Draft

Current recommendation: hold submission until the next milestone, `PR #868 parity rerun readiness`, is complete.

That milestone is complete when:

- the challenge manifest and validation-shard surface are captured automatically in run artifacts
- the next `#868` rerun path is pinned to that exact eval surface
- the control plane still shows the same `pr868_eval_surface_review` diagnosis or resolves it cleanly

## Why we are not submitting yet

- We completed a full provider-staged `8x H100 SXM` reproduction run of the `#868` cache path and got a very strong internal result: `final_ngram_exact val_bpb 0.09749802`, `eval_time 495.326s`, `artifact_bytes 13,416,133`.
- We are not treating that as a public score because it overshot the published `#868` claim by too much to count as an understood reproduction.
- The current audit narrows the mismatch to likely eval-surface drift, not a base-model mismatch.
- That is exactly the kind of issue we should reconcile before making an external claim or asking for support as if the result were already submission-ready.

## Paste-ready answers

### Brief description of your approach

I’m building a reliable reproduction and submission pipeline for the cache-based Parameter Golf approaches that are currently leading the field. I started with the more conservative score-first cache path around PR #868 so I could establish a defensible baseline before moving to more aggressive variants. To do that, I built a RunPod-based operator with watchdog execution, mirrored logs and state, provider-side shared-cache staging, budget controls, and a control-room reporting layer so I can run serious reproductions without losing time to setup failures or idle infrastructure. I completed a full provider-staged 8x H100 SXM reproduction run of the PR #868 path, which finished with `final_ngram_exact val_bpb 0.09749802`, `eval_time 495.326s`, and total artifact size `13,416,133` bytes. Because that result is materially stronger than the published PR claim, I paused and ran a mismatch audit instead of submitting prematurely; the current leading diagnosis is eval-surface drift from an unpinned challenge-data snapshot. Additional compute would let me pin the exact manifest and validation surface, rerun the conservative path cleanly, and then use the same pipeline on stronger cache targets once the baseline is fully understood.

### What have you tried so far?

I built the full RunPod control plane, validated smoke runs, solved FlashAttention bootstrap and transport bottlenecks, moved reusable assets to provider-side staging, completed a full 8x H100 SXM reproduction run of the PR #868 cache path, and then audited the mismatch instead of treating an unresolved internal result as submission-ready.

### Link(s) to your PR submission

No competition submission PR yet. Working fork and control-plane repo:

`https://github.com/brunner-concepts/parameter-golf`

### Current best leaderboard submission score

No public submission yet.

### What improvement do you expect from additional compute?

More compute would not be used for blind search. The immediate use is to close the current `#868` parity gap responsibly by pinning the exact challenge manifest and validation-shard surface, then rerunning the conservative cache path under those controlled conditions. If that resolves cleanly, I can use the same proven pipeline for confirmation runs and for the strongest next cache targets. The value of additional compute here is not just a lower score; it is turning a strong but unresolved internal result into a defensible, competition-valid submission path.

## Evidence to cite if needed

- Self-funded RunPod reloads observed so far: `$550`
- Sponsored credit observed so far: `$25`
- Full `#868` repro report: `09_RESULTS/repro_pr868_full.md`
- `#868` mismatch audit: `09_RESULTS/repro_pr868_mismatch_audit.md`
- Current control-plane diagnosis: `11_RUN_CONTROL/control_plane/state/working_memory.md`
