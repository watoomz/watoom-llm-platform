---
name: systematic-debugging
description: Use for any bug, failing test, build error or unexpected behaviour, before proposing a fix. Find the root cause with evidence first; one change at a time; stop and rethink after three failed fixes.
---

# Systematic debugging

Iron rule: **no fix until you know the root cause.** A fix for a symptom is a new bug.

## Phase 1: investigate (before any change)

1. **Read the error in full**: message, file, line, code. It often names the cause.
2. **Reproduce it reliably.** If you cannot, collect more data; do not guess.
3. **Check what changed**: recent edits, config, versions, the environment.
4. **Multi-part systems** (service to service, build to deploy, device to host): find *where* it breaks by checking what enters and leaves each part, once, before theorising.
5. **Trace backwards** from the bad value to where it first went wrong; fix at the source.

## Phase 2: compare

Find similar working code, read it completely, list every difference, and note the settings and assumptions it relies on.

## Phase 3: one hypothesis

Write "I think X is the cause because Y". Test it with the smallest possible change, one variable at a time. If it fails, form a new hypothesis; do not stack fixes. If you do not know, say so.

## Phase 4: fix

1. Reproduce the bug in the smallest failing check first (see `test-driven-development`).
2. One fix for the root cause. No "while I'm here" edits.
3. Confirm the symptom is gone and nothing else broke (see `verification-before-completion`).
4. **Three failed fixes means the design is probably wrong.** Stop, describe what each fix revealed, and discuss the approach with the operator before trying a fourth.

## You have no shell

Gather evidence with what you can read (files, logs the operator pastes, project readers). When evidence needs a command, hand the operator the exact read-only command (`operator-commands`) and wait for the output; do not guess in the meantime. Prefer adding diagnostics (logging, an extra check) to guessing at fixes.

## Stop signs

"Quick fix now, investigate later", "just try changing X", several changes at once, proposing a fix before tracing the data, "one more attempt" after two failures. Return to Phase 1.

Ported and condensed from obra/superpowers (MIT), see `superpowers-LICENSE`.
