# Shared Blender worker helpers

Single source for the helper files 20+ Blender skills carry (`scripts/_worker_runtime.py`, `_bpyx.py`,
`worker_profile.py`, `worker-profiles.json`, `references/worker-execution.md`). Edit them HERE, then run
`scripts/sync-skill-shared.py` to refresh every skill copy; `sync-skill-shared.py --check` fails on drift.
The copies stay inside each skill because skills are installed and rsynced to workers as self-contained trees.
