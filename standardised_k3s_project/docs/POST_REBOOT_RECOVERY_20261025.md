# Reboot recovery, 25 October 2026

GPU unlock was confirmed in the kernel log after the authorized systemctl reboot.
Qwen uncensored MTP loaded its read-only CPU projector and passed both swapped-
colour image probes again. Existing model weights, context and MTP were preserved.
Dispatcharr returned HTTP 200 with the Dispatcharr page title at
http://10.99.20.225:9191. k3s and Docker are active; historical exited fixture
containers and intentionally inactive model deployments were not started.

Observability exposed a stale hostPath dependency after reboot: the retired
/data/ai/projects/legacy-workspaces/opencode-workspace/.opencode-runs directory
no longer exists. Its optional legacy input now uses an emptyDir, while existing
container/pod log mounts remain unchanged. This does not fabricate historical
run records or claim coverage of native SQLite sessions through a legacy exporter.
Only that Deployment was applied after server-side dry-run validation.
The previous Deployment and recovery manifest are saved in the reboot evidence.
Rollback restores that exact Deployment; doing so requires the legacy input to
be explicitly supplied and reviewed, or the same missing-directory failure returns.

Evidence: /data/ai/helper-scripts/reports/gpu-unlock-af28cbbf/reboot-20261025.
The user stopped the render monitor; it remains paused. Completed capture evidence
and the standing/seated coordinator checkpoint are preserved. Enabling vision
does not mark either requested final render complete or replay previous jobs.
