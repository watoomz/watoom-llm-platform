# WatooM OpenCode Coding Workspace

This directory is the persistent project workspace.

## Workspace rules

- Work only under `/workspace`, except OpenCode-managed temporary paths.
- When the user explicitly asks to create or modify a coding project, keep that project in its own subdirectory under `/workspace`.
- Do not create a project directory for informational requests, diagnostics, command-verification requests, or simple inspections.
- Put final source code, intentionally generated build artefacts, documents, archives, and handoff files under the relevant project directory.
- Prefer project-local dependency manifests and virtual environments.
- Do not expect Docker/Podman or the host filesystem unless the environment explicitly proves otherwise.

## Tool discipline

- Perform only work required by the active assignment.
- Never issue the same tool call with identical arguments more than once in the same assistant response.
- Do not repeat a successful command merely to verify it succeeded.
- For dependent actions, run one action and inspect its result before deciding the next action.
- Parallelise only genuinely independent work.
- Do not create demonstration projects or scratch files unless required.
- Once the requested result is obtained, stop inventing follow-up work.

## Git safety

- Do not use `git add .`, `git add -A`, `git reset --hard`, `git clean -fd`, `git checkout .`, or broad `git restore`.
- Do not commit, amend, or push unless the original user request explicitly authorises it.
- Stage only specifically intended files when staging is explicitly requested.

<!-- BEGIN WATOOM MODULAR AGENT RULES V1 -->
## Modular WatooM engineering rules

The stable rule library is under `/workspace/.watoom/agent-rules/`.

Every bounded task uses universal and homelab rules plus only technology-specific rules selected from repository evidence. The runner may inject a compact selected rule bundle into the assignment. Apply only that selected bundle; do not load unrelated rule files.

Repository evidence overrides generic defaults. Discover the actual test framework, package manager, build system, formatter, linter, runtime and IaC conventions rather than assuming common defaults.

Kali/security workflows use the same modular-rule concept, but OpenCode reasoning never replaces target authorization, installed-version tool evidence, LOTCE policy/argv validation, or the bounded execution wrapper.
<!-- END WATOOM MODULAR AGENT RULES V1 -->
