# Data Surfaces

This directory holds frozen challenge-data artifacts that are safe to commit and safe to reference from generated run specs.

For the current `#868` parity campaign, the operator expects:

- `pr868_manifest_snapshot.json`
- `pr868_surface_snapshot.json`

Those files are the source of truth for:

- the exact challenge `manifest.json` used by the rerun
- the pinned Hugging Face dataset revision
- the expected validation-shard inventory

Generate or refresh them with:

```bash
python3 scripts/freeze_challenge_data_surface.py
```

Do not point parity reruns at an unpinned remote manifest. The whole purpose of this directory is to eliminate eval-surface drift as an ambiguity source.
