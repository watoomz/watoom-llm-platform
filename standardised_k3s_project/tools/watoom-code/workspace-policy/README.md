# Homelab/LLM workspace policy

Native tool middleware enrolls only new top-level sessions in the registered Homelab/LLM directory after the installation cutoff. Existing sessions, IDX and unrelated locations are not enrolled. Children inherit their parent boundary; relocation is rejected. Direct writes/edits stay within the independent checkout. Git metadata, runtime configuration, all shell/code execution, unknown tools and external workers are denied for enrolled sessions. Existing native permissions still apply. Canonical Git remains mounted read-only.

This is conservative tool mediation, **not OS filesystem isolation**. No arbitrary shell, tests, Git commit/push or worker route is advertised as isolated. Those routes remain unavailable until an OS sandbox is qualified. Operator validation and dev integration occur separately on the host. Do not silently weaken the boundary to enable them.

The native package replaces only the old homelab-task-checkout-guard registration. It does not modify coordinator options, grants, sessions or IDX files. New location boot loads it without a global restart. Reprovisioning preserves enrollment cutoff. Retain the previous package and private config backup for rollback.
