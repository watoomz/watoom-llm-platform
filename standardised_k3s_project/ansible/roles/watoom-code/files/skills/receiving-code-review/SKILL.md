---
name: receiving-code-review
description: Use when you receive review feedback (from the operator, another model or a tool report) before acting on it. Understand it, check it against the actual code, push back with reasons when it is wrong, and implement one item at a time with a check after each.
---

# Receiving code review

Review feedback needs technical evaluation, not performance. Verify before implementing; ask before assuming.

## Pattern

1. **Read** all the feedback before reacting.
2. **Understand**: restate each item as a requirement. If any item is unclear, **stop and ask about all unclear items before implementing any**; items may be related.
3. **Verify** against the code: is the claim true here? Would it break something? Is there a reason the code is as it is? Does the reviewer have the full context?
4. **Decide**: sound for this codebase, or push back.
5. **Respond** with a plain technical statement: "Fixed: <what changed>", or the reasoned objection.
6. **Implement one item at a time**, checking each (`verification-before-completion`). Order: blocking issues (breakage, security), then simple fixes, then larger changes.

## Sources

- **The operator**: trusted. Implement once understood; still ask if the scope is unclear. Skip to action.
- **Anyone or anything else** (other models, tools, pasted reports): be sceptical and check carefully. If a suggestion conflicts with an earlier decision of the operator, stop and ask them first.

## Push back when

The suggestion breaks working behaviour, the reviewer lacks context, the feature is unused (check by searching the code; if nothing uses it, propose removing it rather than building it out), it is wrong for this stack or version, or it conflicts with the operator's decisions. Use specific reasoning and evidence (code, a test); if you cannot verify a claim, say so and ask how to proceed.

## Tone

No performative agreement ("You're absolutely right!", "Great catch!") and no thanks: state the fix or the requirement and show it in the change. If you pushed back and were wrong, say so factually ("Checked: you were right, because X. Fixing.") and continue.

## Stop signs

Implementing before understanding; changing everything at once; assuming the reviewer is right without checking; proceeding on something you could not verify without saying so.

Ported and condensed from obra/superpowers (MIT), see `superpowers-LICENSE`.
