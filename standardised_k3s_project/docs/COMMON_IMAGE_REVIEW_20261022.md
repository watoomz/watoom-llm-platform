# Common project image review location

Owner-requested shared location: `/data/ai/projects/images/review`.

`projects/` preserves project-relative render/capture/preview/validation paths. Images are copied, not moved, with content-hash filename suffixes and JSON sidecars recording original path, SHA256, bytes and source timestamp. Changed captures retain earlier versions. The authoritative image_review role installs a CPU-limited one-minute systemd collector, integrated into the normal role and available through the scoped watoom-code-image-review.yml playbook. The initial backfill includes existing project and published worker capture directories, preserving originals.

`viewed/<session-id>/` records actual native image-read results, including individual reference or intermediate images used during a run. The maintained native plugin saves returned image bytes plus source/session/hash metadata before returning the tool result. Copy errors are exposed in tool metadata and plugin storage, without replaying a completed generation. All agent roles document the shared review contract and reporting paths. Original purchased texture libraries are not bulk-mirrored merely because they exist.

Tests cover exact-byte copy, deduplication, changed-version retention, provenance, symlink rejection and exclusion of unrelated raw textures. The native guard regression suite passed. Production activation and backfill evidence: `/data/ai/helper-scripts/reports/common-image-review-20261022`.
