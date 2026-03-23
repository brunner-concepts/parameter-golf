# North Star

Your north star is not "get the lowest BPB in a spreadsheet."

It is:

**Ship the earliest legally defensible PR that has a credible path to being accepted as the new record.**

That is the objective the whole system should optimize for, because the challenge accepts records chronologically and distinguishes between the official leaderboard and the live/pending frontier. README also makes legality and significance part of winning, not just the raw number.

## Four nested goals

**1. Win officially, not cosmetically.**
A flashy score that later gets challenged on TTT legality, eval procedure, or artifact accounting is not the win you want. The rules explicitly constrain evaluation-time adaptation to already-evaluated validation tokens, and the live tracker discussion shows that this distinction is active and consequential right now.

**2. Maximize accepted-record probability per day of research.**
This challenge is not a pure science project. It is a race under chronology, public PR visibility, and a fast-moving frontier. Prefer a slightly less glamorous but more reproducible, more legible, more PR-ready path over a fragile moonshot. README explicitly warns participants to pay attention to the current SOTA PR because acceptance is chronological.

**3. Treat intelligence as capital allocation.**
Your job is not to invent every idea yourself. Your job is to allocate agent attention into the highest expected-value lanes:
- reproduce the strongest defensible base,
- transfer only the most promising legal improvement,
- kill weak branches fast,
- package immediately when evidence is good enough.

**4. Build a machine that compounds evidence.**
The real asset is not a single experiment. It is a research loop that preserves context, measures runtime and artifact size correctly, enforces legality, and turns every run into a better next decision. In this contest, many ideas fail because they lose on throughput or byte budget even when they look good conceptually.

## One-line slogan

**"Earliest accepted record, not prettiest model."**

## Operational priorities

1. Reproduction before invention
2. Legality before bravado
3. Runtime before elegance
4. PR-readiness before endless optimization

## Current primary thesis

The strongest legal path is likely: start from the strongest non-TTT base (#505, GEPA, 1.1181), add only legal score-first evaluation adaptation, and package fast enough to win chronology.

Public evidence: #505 is the strongest non-TTT frontier. Legal TTT already transfers on standard bases (#508 at 1.1215, #503 at 1.1218, #473 at 1.1220). GEPA + legal TTT has not been attempted yet — that is the gap.

## Track allocation

- 60% compute/attention: Track A — GEPA + legal TTT
- 30%: Track B — #414-family + legal TTT hardening
- 10%: Track C — micro-delta experiments only

## Project memory

The following files are the only durable memory for this project. Read them before every session. Update them after every decision.

| File | Purpose |
|------|---------|
| `00_EXECUTIVE_BRIEF.md` | Goal, targets, track allocation, top hypotheses, stop/go |
| `01_RULES_AND_LEGALITY.md` | Competition constraints, TTT legality protocol |
| `02_FRONTIER_STATE.md` | Leaderboard, live tracker, key PRs, interpretations |
| `03_SYSTEM_ARCHITECTURE.md` | Agent roles, execution phases, feedback loop |
| `04_EXPERIMENT_POLICY.md` | Decision function, promotion gates, hard constraints |
| `05_HYPOTHESIS_BACKLOG.jsonl` | Prioritized hypothesis queue |
| `06_EXPERIMENT_REGISTRY.jsonl` | Every experiment logged |
| `07_DECISION_LOG.md` | Major decisions and rationale |
| `08_PROMPT_CONTRACTS/` | Reusable agent prompts |
| `09_RESULTS/` | Structured experiment reports |
| `10_SUBMISSION_STAGING/` | PR-ready artifacts |
