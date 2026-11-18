# Automatic image result display

New MCP submissions persist their originating native session from authenticated MCP request metadata. Existing unassociated jobs remain unchanged. Idempotent retries cannot rebind a job to another session.

The authenticated read-only native `GET /api/session/:sessionID/images` endpoint reads that session and actual descendants (bounded at 32 sessions). It calls only `list_session_images` and, for a requested verified job, `image_result`. No prompt admission, synthetic inbox entry, session resume, model switch, or generation retry occurs on result reads.

The chat footer polls pending jobs every five seconds while selected, displays failures without replay, and renders a downloadable PNG only after the worker and native reader verify dimensions, SHA-256 and prior-model restoration. A temporary unavailable service is retried every fifteen seconds. Reopening the chat recovers results from existing durable worker receipts; the browser need not remain open during generation.

Historical jobs are not adopted or replayed. The existing worker owns GPU handoff, restoration and durable completion. Descriptions, prompts and model settings are not copied into result delivery records.

Validation evidence: `/data/ai/helper-scripts/reports/image-result-delivery-20261021`. Full repository check is limited by an existing missing `@tsconfig/node22` dependency in the unrelated console package; affected-package checks are run independently.

Production validation passed: 95 Model Manager tests; all five affected app packages type-check; exact-image admission, authentication and rollback checks; neutral 512x512 SDXL generation with Defiant restoration; automatic chat rendering, checksum-matched PNG download, mobile layout, cold receipt discovery and failure display without replay. Read-only result retrieval was verified while native inference admission remained fenced, with unchanged session messages. All 27 prompt-builder pipelines pass after catalog warmup. The initial cold catalog transient and the earlier five-minute browser timeout during model restoration are retained in the evidence directory. Production deployment and live skill guidance are verified. Isolated candidate resources were removed; evidence remains.
