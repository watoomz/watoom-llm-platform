---
name: security-review
description: Explicit read-only security review methodology for trust boundaries, secrets, command execution, path validation, authorization, and unsafe defaults.
metadata:
  opencode/autoinvoke: false
---

# Security review

Check evidence for:

- authorization and trust boundaries;
- path traversal / external-directory escape;
- shell/argv construction and injection;
- secrets exposure;
- unsafe defaults/fail-open behavior;
- excessive permissions;
- destructive operation gating;
- network target scope;
- cleanup/timeout/resource exhaustion.

Report concrete findings only. Separate exploitable defects from hardening ideas.
