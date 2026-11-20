---
name: watoom-openspec
description: WatooM integration policy for persistent OpenSpec changes.
---

# WatooM OpenSpec

Use OpenSpec for substantial work where persistent requirements, design,
implementation tasks, or cross-session state are useful.

Do not create an OpenSpec change for trivial edits or simple factual
investigation.

## Ownership

OpenSpec owns:

- proposal/change intent;
- specifications and requirements;
- design rationale when needed;
- task progress;
- change verification state;
- archived change history.

WatooM repository policy owns:

- permissions;
- security boundaries;
- evidence requirements;
- implementation conventions;
- IaC authority;
- Git safety;
- validation requirements.

OpenSpec never grants permission to perform an action.

## Milestones

Alongside `proposal.md`, maintain a `milestones.md` file in the change
directory for any change with more than one meaningful delivery point.
Keep it a simple list, one milestone per entry:

```markdown
---
milestones:
  - name: <short name>
    target_status: <artifact or status this milestone completes>
---
```

Update it as milestones complete. Do not fabricate milestones for a
single-step change; a `tasks.md` list is enough on its own in that case.

## Acceptance criteria

Every `proposal.md` must include a `## Acceptance Criteria` section
stating, as a checklist, the concrete conditions that must hold for the
change to be considered done. Write these when the proposal is drafted,
not retroactively at archive time. If the user's intent is ambiguous
enough to affect acceptance criteria, ask before writing them rather than
guessing.

## Discord notifications

Notify Discord at two points, using
`~/.config/opencode/watoom-tools/watoom-openspec-notify.py`. The webhook
URL is never passed inline; it is read by the script from a root-only
file path given via `--webhook-file`, which is supplied by the invoking
project's own configuration (do not hardcode a path here).

- **Status change**: after any step that changes a change's recorded
  status (an artifact completes, `openspec archive`, `openspec apply`),
  run the script with `--status --change "<name>" --from-status <old>
  --to-status <new> --project "<repo/project name>"`. When available,
  add `--change-dir "<path-to-project>/openspec/changes/<name>"` so the
  embed can include the proposal summary, acceptance-criteria progress, and
  milestone progress.
- **Blocked / needs input**: whenever you report to the user that a
  change is blocked or needs their decision, also run the script with
  `--blocked --change "<name>" --reason "<short reason>" --project
  "<repo/project name>"`. When available, add
  `--change-dir "<path-to-project>/openspec/changes/<name>"` to include
  the proposal context and completed tasks alongside the reason.

`--change-dir` is optional. It points to the actual change directory (the
directory containing `proposal.md`, `tasks.md`, and optionally
`milestones.md`); missing files or an unavailable directory simply omit
those enrichment fields.

A failed notification is not a blocker for the underlying OpenSpec work;
report it and continue rather than retrying indefinitely.

## Investigation

Before committing a substantial change design, establish current state.

Use `watoom-investigator` when fresh-context investigation is useful.

Never convert an assumption into a specification merely because OpenSpec needs
an artifact populated. Record unresolved facts as uncertainties and gather
evidence.

## Implementation

Apply only the active change's intended scope.

Existing AGENTS.md files and domain skills remain authoritative for how work is
performed.

Preserve unrelated dirty work.

Do not stage, commit or push unless explicitly requested.

## Verification

OpenSpec verification supplements rather than replaces actual validation.

For infrastructure work, verify both:

1. authoritative source state;
2. relevant resulting live state.

A validation command that did not run is not a pass.

Use `watoom-reviewer` for independent review when the change is substantial,
security-sensitive, cross-cutting, or has meaningful regression risk.

## Archive

Archive only after:

- intended tasks are complete;
- required validation has actually run;
- relevant live verification has passed where applicable;
- unresolved limitations are recorded.

Do not archive merely because implementation files were edited.
