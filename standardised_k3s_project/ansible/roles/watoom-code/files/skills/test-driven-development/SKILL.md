---
name: test-driven-development
description: Use when adding behaviour or fixing a bug in code that can be tested. Write the failing test first, see it fail for the right reason, write the minimum code to pass, then clean up. Where you cannot run tests, hand the operator the command.
---

# Test-driven development

Iron rule: **no production code without a failing test that demands it.** Code written before its test gets deleted and redone from the test.

## Cycle

1. **Red**: write one small test for one behaviour, with a clear name and real code (mock only what you must).
2. **Check red**: run it and confirm it fails *because the behaviour is missing*, not because of a typo or import error. A test that passes immediately proves nothing: fix the test.
3. **Green**: write the simplest code that passes. No extra options, no future-proofing.
4. **Check green**: run the new test and the rest of the suite; both clean.
5. **Refactor** only while green: remove duplication, improve names. Do not add behaviour.
6. Repeat for the next behaviour.

## Bug fixes

Reproduce the bug as a failing test first, watch it fail, fix, watch it pass. The test then guards the regression. To prove it, revert the fix once and confirm the test fails again.

## Good tests

One behaviour each; names that say what is expected; they test observable behaviour, not private details; no sleeping or timing guesses (wait on a condition).

## You have no shell

You cannot run the suite. Write the test and the code, then follow `operator-commands`: give the operator the exact test command and a revert command, and state which results you expect (red first, then green). Report the work as unverified until they return real output (`verification-before-completion`). Do not claim red or green you did not see.

## Stop signs

Code before the test; a test that passed first time; "I'll add tests after"; keeping untested code "as a reference"; tests that only check mocks. Start the cycle again from the test.

Ported and condensed from obra/superpowers (MIT), see `superpowers-LICENSE`.
