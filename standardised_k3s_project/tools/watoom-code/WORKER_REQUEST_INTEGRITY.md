# Native worker request integrity

Worker protocol directories (worker-requests, rig-worker-requests,
asset-capture-requests, esp32-requests) are runtime-owned. Model write/edit/patch
operations targeting those paths are rejected; shell references must use native
worker status or read instead. Declarative capture-jobs manifests remain writable.

Game/capture/ESP32 tools validate the immutable request identity before reporting
QUEUED. A mismatched message/call/revision identity reports WORKER_REQUEST_CORRUPTED
and requires operator reconciliation. It must never cause another job to be created
or justify an endless wait. A pending external request also blocks shell sleep loops.
These checks route ordinary model operations; they do not replace an OS shell sandbox.

A completed subagent that reports a worker request ID with no matching protocol
file is rejected with CHILD_CLAIM_UNVERIFIED and must be continued, not relayed.
2026-11-04: a builder compacted mid-package, made no further tool calls, then
reported an invented zas-regression-3 request_id as QUEUED.

For a corrupted original server game request, repair_game_request.py is the
operator-only recovery entry point. It takes --project, --request-id, --database
and --evidence; reads the actual native admission; requires exactly one completed
matching tool call; checks current source identity and absence of prior execution;
backs up the corrupted file exclusively; and restores the SAME request atomically
under the dispatcher lock. It refuses invented, ambiguous, stale or executed jobs.
Never change IDs by hand or replay a terminal request.

Deploy the main guard with the scoped coordinator-guard playbook under a native
idle release fence. The isolated RIG app uses tools/rig-async-stage/update-guard.py
with its own fence, database snapshot, immutable plugin path and rollback.

Regression: test-worker-request-integrity.mjs and test_repair_game_request.py, plus
existing coordinator, game worker, asset capture and staged RIG native suites.
2026-10-26 recovery: 452fbf7201eecda457c7bc3a706892440f56a3071e1d847cf339b92bf65c7fd7
ran once after restoration and correctly reported FAILED for real terrain script
errors (array index 2; missing amp key), with source_matches:true. No visual PASS.
