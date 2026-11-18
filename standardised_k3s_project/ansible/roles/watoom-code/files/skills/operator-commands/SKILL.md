---
name: operator-commands
description: Use whenever a task needs a shell command, root access, systemctl, kubectl, ansible, package installs, flashing, or any action your tools cannot perform. Do not try workarounds; hand the operator the exact command plus a revert command, then wait.
---

# Handing commands to the operator

You do not have shell or code execution. That is deliberate. When progress needs something run that you cannot run,
**do not** look for a bypass (alternate tools, encoded commands, writing scripts that something else will execute, asking
another agent to run it). Give the operator the command instead and continue with everything you can still do.

## What to hand over

Give **one block per action**, in this order:

1. **Why** (one sentence): what it achieves and what in the task needs it.
2. **Command** (single copy-paste block): complete, exact, absolute paths, no placeholders left unfilled, no secrets.
   If several steps are needed, number them and keep each step independently runnable.
3. **Check** (one command or expected output) so the operator can confirm it worked.
4. **Revert** (single copy-paste block): the exact inverse. If the action overwrites or deletes anything, put the
   **backup step inside the Command** (for example `cp -a FILE FILE.bak-$(date +%Y%m%d%H%M)`) and make Revert restore it.
   If something genuinely cannot be undone, say so in bold and require an explicit "go" from the operator first.
5. **Risk** (one line): what could break, what it touches (services, production state, GPU owner, files outside the project).

Then stop and say what you will do when the operator reports the result. Do not assume it ran.

## Rules

- Prefer the repository's own tools, roles and scripts over ad-hoc commands, and dry-run options first (`--check`, `--dry-run`).
- Never put credentials, tokens or plaintext secrets in a command; reference the file or secret store instead.
- Never ask the operator to disable a security control, loosen permissions broadly, or run `git add -A`, `git reset --hard`, `git clean -fd`, or push `main`.
- Hardware and live production state (flashing, GPU ownership, services, cluster changes): name the exact device or unit, and say whether a reset or restart happens.
- Keep it short. One action, one block. If the task needs ten commands, hand over the first and say the rest follow.

## Example

> **Why:** the ESP32 needs the 600 s capture window deployed.
> **Command:** `cp -a /etc/systemd/system/x.service /etc/systemd/system/x.service.bak-$(date +%Y%m%d%H%M) && systemctl restart x`
> **Check:** `systemctl is-active x` prints `active`.
> **Revert:** `cp -a /etc/systemd/system/x.service.bak-… /etc/systemd/system/x.service && systemctl restart x`
> **Risk:** restarts the worker; an in-flight job is cut off.
