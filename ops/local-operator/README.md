# Local Operator

This is the local, sandboxed operator loop for the Parameter Golf project.

## Purpose

Run a narrow autonomous control plane on this Mac without exposing extra host surface:

- one Docker container
- repo bind mount
- read-only RunPod credentials
- localhost-only dashboard
- no Docker socket
- no privileged mode
- no host networking

## Start

Make sure Docker Desktop or another Docker daemon is running first.

```bash
export RUNPOD_HOME=$HOME/.runpod
docker compose -f docker-compose.local-operator.yml up -d --build
```

Dashboard:

- `http://127.0.0.1:8787`

Logs:

```bash
docker compose -f docker-compose.local-operator.yml logs -f operator
```

Stop:

```bash
docker compose -f docker-compose.local-operator.yml down
```

## Behavior

The daemon:

- polls the frontier and budget
- syncs tracked upstream PR targets into ignored runtime state
- ranks targets by accepted-record probability
- auto-generates guarded run specs
- may auto-launch only approved specs within hard daily caps
- writes executive state that a separate host-side repair controller can use for bounded self-repair and autonomous review resolution

It does **not**:

- push to GitHub
- open PRs
- let advisory sidecars spend compute
- expose the dashboard on a non-localhost interface

## Codex Automation

The Codex app can be used as a scheduled read-only observer over this repo, but it should not replace the repo control plane.

Use the prompt in `ops/local-operator/codex_automation_prompt.md` to create a daily Automation against this local project.

Recommended role for that Automation:

- read `11_RUN_CONTROL/control_plane/state/status_snapshot.json`
- compare it against the latest reports and decision log
- produce a short executive check-in

Do not use the Automation to launch pods or mutate repo state. The operator, not the scheduled thread, remains the execution engine.

## Host-side repair controller

The Docker operator intentionally does not hold local Codex/Claude CLI auth. The write-authorized repair lane runs on the host instead:

```bash
python3 scripts/repair_controller.py
```

Recommended long-lived deployment:

- run it in `tmux` on the host
- leave the Docker operator responsible for queueing/launching
- let the repair controller consume `11_RUN_CONTROL/control_plane/state/repair_queue.json` and resolve deterministic target-family failures or completed parity reviews automatically

This keeps model-authenticated repair authority outside the container while still preserving a single file-backed source of truth under `11_RUN_CONTROL/control_plane/state/`.
