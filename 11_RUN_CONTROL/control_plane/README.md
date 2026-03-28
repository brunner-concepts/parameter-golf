# Control Plane

`11_RUN_CONTROL/control_plane/` holds the tracked defaults for the local autonomous operator.

Tracked files:

- `operator_policy.json`: hard guardrails for budget, target ranking, and autonomy

Ignored runtime directories:

- `state/`: latest operator state, budget, frontier, and queue snapshots
- `generated_specs/`: daemon-generated run specs for the current frontier targets
- `advisory/`: legality and target-selection memos
- `upstream_prs/`: live-synced upstream record files for the operator loop

The local operator daemon uses these defaults but never pushes changes automatically.

Main command:

```bash
python3 scripts/control_plane_daemon.py \
  --policy 11_RUN_CONTROL/control_plane/operator_policy.json \
  --state-root 11_RUN_CONTROL/control_plane/state
```

Dry-run the control plane without spending:

```bash
python3 scripts/control_plane_daemon.py --once --no-launch --no-dashboard
```
