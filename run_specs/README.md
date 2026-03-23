# Run Specs

Run specs are durable JSON files that describe one experiment at a time.

They are designed to work with [scripts/run_watchdog.py](/Users/brandonrunner/Projects/runner-concepts-projects/openai-project-golf/scripts/run_watchdog.py) and enforce the operating rules from [north-star.md](/Users/brandonrunner/Projects/runner-concepts-projects/openai-project-golf/north-star.md) and [04_EXPERIMENT_POLICY.md](/Users/brandonrunner/Projects/runner-concepts-projects/openai-project-golf/04_EXPERIMENT_POLICY.md):

- one hypothesis per spec
- one compute tier at a time
- no auto-promotion to more expensive runs
- explicit success/failure summaries

## Minimal schema

```json
{
  "schema_version": 1,
  "run_id": "repro_pr414_smoke",
  "hypothesis": "Smoke-test the PR #414 stack before spending 8x H100 compute.",
  "parent_branch": "repro/pr414",
  "track": "B",
  "compute_tier": "1xH100-smoke",
  "auto_promote": false,
  "promotion_gate": "Smoke must be clean before 8x repro.",
  "env": {
    "REPO_DIR": "/workspace/parameter-golf"
  },
  "phases": [
    {
      "id": "bootstrap_env",
      "description": "Prepare repo, venv, and required imports.",
      "command": "bash scripts/bootstrap_runpod_env.sh",
      "cwd": "${REPO_DIR}",
      "log_name": "bootstrap_env.log",
      "failure_summary": "Fix bootstrap on the same tier before retrying."
    }
  ],
  "success_summary": "Review the run before allocating more compute.",
  "manual_next_spec": "run_specs/repro_pr414_full.json"
}
```

## Usage

Validate:

```bash
python3 scripts/run_watchdog.py validate run_specs/repro_pr414_smoke.json
```

Dry-run:

```bash
python3 scripts/run_watchdog.py run run_specs/repro_pr414_smoke.json --dry-run
```

Real run:

```bash
python3 scripts/run_watchdog.py run run_specs/repro_pr414_smoke.json
```
