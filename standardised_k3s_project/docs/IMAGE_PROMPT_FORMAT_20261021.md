# Image prompt layout and session check — 2026-10-21

The image skill opts into a validated `prose-tags` display contract. The copied
prompt starts with a positive block: one descriptive paragraph followed by
comma-separated quality/visual tags. A blank description falls back to the main
request. Tags are trimmed and deduplicated. Negative scores and exclusions stay
in a separate negative block; an empty block is omitted. Execution settings,
project path, skill routing and coordinator guidance remain outside image text.
Other pipelines retain their existing output. Pony scoring applies only when a
selected model card supports it. No content from the supplied example was used
in test fixtures; neutral park/bench scenes were used throughout.

This UI change does not add negative-prompt support to the GPU API. The copyable
negative block is retained separately and must not be claimed applied by that
worker. No image request was submitted by the form or browser tests.

12 focused tests and app typecheck passed. Exact-image candidate checks covered
native admission refusal, authenticated API/GUI, engineering tools, memory and
rollback using a copied existing fixture; no user/AI session was created. The
existing guard checker accepts the observed fenced-prompt HTTP 500 refusal;
unchanged messages and no active execution were independently verified. This
status was retained as evidence rather than changing the guard.

Candidate and production browser checks verified 27 pipelines, the prose/tag
layout, negative separation, clipboard/fallback, mobile layout and zero session
or job submissions. Production UI was visually inspected. The owning guarded
release helper persisted the immutable image in IaC, preserved model/MCP settings,
verified existing adapters and reopened admission after acceptance. Only the
owned temporary candidate deployment/service were removed; evidence is retained.

Latest session ses_ea367bc6effdtkB4DCdAjDJzAG was idle. Its actual image job was
GENERATION_VERIFIED. One coordinator retry hit COORDINATOR_CRITIC_REQUIRED and
was followed by critic review. The GPU worker was not stuck. The asynchronous
image route deliberately ends a native turn before GPU execution; chat does not
automatically resume itself. No task was resumed or steered during this audit.

App source commit: 98f837210f2ee900bb848f28fcc2ffea6fb69e15
Image: 127.0.0.1:5000/watoom-code@sha256:d1a4dfbb1f3c3bab4e48cec8233ae02fc58eed0e492df7be3c6745f167732154
Evidence: /data/ai/helper-scripts/reports/latest-session-format-20261021
