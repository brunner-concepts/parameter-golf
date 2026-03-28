# Codex Automation Prompt

Use this in the Codex app when creating a scheduled Automation for this local project.

## Recommended configuration

- Title: `Parameter Golf Executive Check`
- Project: `/Users/brandonrunner/Projects/runner-concepts-projects/openai-project-golf`
- Schedule: daily at `9:00 AM` local time
- Goal: read-only executive refresh, not execution

## Prompt

Read the Parameter Golf control-plane state and produce a concise executive check-in.

Source of truth, in order:

1. `11_RUN_CONTROL/control_plane/state/status_snapshot.json`
2. `11_RUN_CONTROL/control_plane/state/working_memory.md`
3. `11_RUN_CONTROL/control_plane/state/executive_state.json`
4. `09_RESULTS/repro_pr868_full.md`
5. `09_RESULTS/repro_pr868_mismatch_audit.md`
6. `07_DECISION_LOG.md`
7. `git log -1 --oneline`

Answer these exactly:

- What changed since the last automation run?
- What is the current diagnosis and next autonomous action?
- Is the system blocked by review, budget, or infrastructure?
- Are the repo, control-plane state, and latest result narrative aligned?
- What is the exact next milestone?
- Is the grant/application narrative ready, or still waiting on the next milestone?
- Is any competition PR submission warranted right now?

Constraints:

- Do not mutate files.
- Do not launch compute.
- Treat repo state as authoritative, not any prior chat memory.
- If the status snapshot and raw state disagree, call that out explicitly and trust the newer timestamp.
- Keep the answer concise and decision-oriented.
