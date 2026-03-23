# System Architecture

## Agent roles

### 1. Chief of Staff / Program Manager

Owns: source of truth files, experiment queue, stop/go decisions, branch naming, artifact hygiene, final PR packaging.
Never writes model code. Only coordinates.

### 2. Frontier Intelligence Agent

Owns: syncing 02_FRONTIER_STATE.md, extracting hyperparams from public PRs, identifying legality risk, producing delta memos when frontier moves.
Only reads public sources and updates the internal brief.

### 3. Reproduction Agent

Owns: exact reproduction of known bases, no creative changes, branch purity, matching reported config and artifact size.
Most important worker at the start.

### 4. Architecture Agent

Owns: localized model changes, one hypothesis per branch, explicit latency/byte budget, implementation notes.

### 5. Training Systems Agent

Owns: throughput, kernel choices, memory behavior, profiling, eval-time runtime budget.

### 6. Quantization / Packaging Agent

Owns: quant tax, export path, GPTQ/QAT knobs, zstd profile, artifact byte accounting.

### 7. Evaluation Agent

Owns: exact measurement, step time, pre/post-quant BPB, legal TTT protocol enforcement, seed aggregation.

### 8. Submission Agent

Owns: record eligibility checklist, concise PR description, logs/artifacts/plots/checksums.

## Execution phases

### Phase 0: Bootstrap
- Fork upstream, pin commit hash
- Mirror rules into 01_RULES_AND_LEGALITY.md
- Ingest frontier state into 02_FRONTIER_STATE.md
- Generate first hypothesis queue

### Phase 1: Mandatory reproductions
Execute in order:
1. Reproduce #414 (standard non-TTT)
2. Reproduce #508 or #503 (legal TTT on standard stack)
3. Reproduce #505 (GEPA no-TTT)

No branching until at least two are within tolerance.

### Phase 2: Confidence intervals
For each reproduced base:
1. 1 quick smoke run
2. 1 full proper run
3. 3-seed only if promotion threshold crossed

### Phase 3: Portfolio execution
Run parallel branches:
- `trackA/gepa-legal-ttt`
- `trackB/std414-legal-ttt`
- `trackC/microdelta-only`

### Phase 4: Ruthless culling
Kill any branch that fails gates.

### Phase 5: PR-first behavior
If a branch plausibly clears accepted-record territory, stop searching and package immediately.

## Recursive feedback

Each agent writes a structured report after every run:
- hypothesis, parent branch, exact diff
- train step time, eval time, artifact size
- pre-quant BPB, post-quant BPB
- legality risk
- recommendation: promote / kill / revise

Chief of Staff then updates: 05_HYPOTHESIS_BACKLOG.jsonl, 06_EXPERIMENT_REGISTRY.jsonl, 07_DECISION_LOG.md

No agent gets to self-promote its own idea.
