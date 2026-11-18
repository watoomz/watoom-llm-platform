# Native skill catalog checkpoint — source only

Ownership: `core/skill/catalog.ts` owns catalog metadata, scoped preferences and on-demand verification. Existing `SkillFile`, `Skill.prepare`, session attachments and native `skill` tool perform loading; acquired skills are not globally registered. Schema/protocol/client generation supplies typed APIs; the existing Skills settings tab presents metadata and approved agent preferences. Semantic AgentMemory, workflow transaction state and GPU ownership stay separate. WP-AM application gate G1 remains pending.

The catalog SQLite connection is read-only. Preferences use the existing native application database with project/repository/agent and optional session ownership. Selection pins content SHA256, upstream commit and complete companion-bundle SHA256, and never approves, executes or grants tools. Loading rechecks approval before and after bounded artifact verification, rejects acquired source markers/symlinks/tampering, and requires a reviewed `watoom-skill.json` manifest. Its version-1 exact fields are `version` and `native_tools`; up to 32 registered and statically allowed native tool IDs are accepted. Missing/unreviewed dependencies remain blocked. No package install, subprocess, network fetch, background server or inference is added to loading.

Verified companion filenames are passed into native `Skill.prepare`, avoiding a second directory scan. Public skill schema remains unchanged. Plugin skill domains deliberately expose only their established `list` method, so extending the client catalog namespace does not confer reviewer or preference authority on plugins.

Validation on the pinned Bun lockfile: 69 WatooM core tests, 32 existing native skill regressions, four real native HTTP tests and two UI metadata tests pass (107 total). Core/server/app type checks pass. Final native frontend build passes in 30.934 seconds wall time, 27.976 seconds CPU, peak 1.5 GiB and zero swap under a 2 GiB limit. No lifecycle scripts or unpinned dependencies were downloaded. Runtime request latency, token overhead and steady-state production RAM/CPU/VRAM are not measured; the owned native loading acceptance disabled inference.

The native HTTP acceptance opens the real 197-entry catalog read-only (88 valid, zero approved), verifies authorization and inaccessible-resource failures, and separately uses an owned approval fixture for agent isolation, foreign-session rejection, native loading without resume, content tamper rejection, revocation and removal. Owned fixture approval does not count as production approval. SQLite close/reopen persistence is tested at the source store layer.

Interactive built-picker acceptance is BLOCKED: the temporary host loopback preview returned HTTP 200, but both SSH forwarded ports returned channel-connect failures and the in-app browser returned ERR_CONNECTION_RESET. No SSH/network policy was changed; preview and tunnels were stopped. The temporary harness is retained only in the evidence directory, not as a runtime component.

Remaining integration work: consolidate the existing offline human approval/promotion prototype with native immutable review; display reviewed dependencies in the native picker; expose agent/session selections through composer suggestions and scoped instruction discovery; prove the interactive built UI against the real registry; test removal/reconciliation of previously attached or queued instructions and measure resource/token overhead. Current revocation blocks future resolution, not historical conversation text. The catalog preference migrations currently have a shared per-connection lock; review consolidation into the native conditional migration registry before permanent integration.

NATIVE_INTEGRATION_STATUS=SOURCE_ONLY_PARTIAL
DUPLICATED_FUNCTIONALITY=No second skill executor; offline approval/promotion consolidation outstanding
TEMPORARY_ADAPTERS=Bounded acceptance harness stopped; ignored local pinned type dependency link only
DEPENDENCY_COUNT_AND_JUSTIFICATION=0 new runtime dependencies; existing pinned Effect/SQLite/native skill parser reused
PERFORMANCE_OVERHEAD=Build measured above; runtime overhead NOT_MEASURED
UPSTREAM_DIVERGENCE=Native catalog/schema/API/settings/loader source changes; generated clients come from native generator
CONSOLIDATION_REQUIRED=Human reviewer authority and promotion, migration registration, composer discovery, queued revocation, interactive acceptance
CLEAN_ARCHITECTURE_GATE=BLOCKED

Production skills remain unmodified, with zero acquired skills approved or activated. This checkpoint is not a production-readiness declaration. Production Toolkit policy remains separately deployed from authoritative IaC; its same-UID credential-isolation limitation and exit-zero receipt false-positive defect remain open. The receipt patch is staged and tested, not built/deployed.
