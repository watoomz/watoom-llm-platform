# platform-workers

`platform-workers` is the canonical consolidated home for CS2 helper processes. The CS2 game server itself remains in namespace `cs2`.

Current Services include:

- `cs2-glance-api`
- `cs2-glance-direct-api`
- `cs2-metadata`
- `cs2-server-tracker`
- `cs2-stats-tracker`
- `platform-workers`

Consumers should use `*.platform-workers.svc.cluster.local` where cluster DNS is needed.

Helpers run only here; do not add standalone helper Deployments, Services or PVCs elsewhere.
