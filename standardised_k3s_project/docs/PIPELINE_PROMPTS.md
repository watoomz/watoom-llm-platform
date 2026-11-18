# Pipeline prompt builder

Open [Prompt Builder in watoom-code](https://watoom-code.internal.homelab.example/prompt-builder), beside Skills. Describe the job, prepare questions, review the editable defaults, build the prompt and copy it into a session. Creating a prompt does not start a job.

The page reads `watoom-prompt-creator` and 30 pipeline-specific skills. Defaults keep jobs bounded; explicit requirements take priority. Unknown dimensions can be proposed in the construction plan. Changing a specification clears the previous output.

For Blender, static props default to under 2,000 triangles and textures at or below 1,024 px. Creature/character defaults are under 50,000 triangles and 2,048 px textures when applicable. All defaults are editable. Exact source identifiers and security authorisation remain explicit inputs.

The Blender workflow incorporates the bench lessons: semantic parts/materials, a dimension/contact plan, packed-source QA, real engine validation and actual visual review.

The final prompt is editable. Clipboard denial falls back to selecting the prompt for your normal copy shortcut.

The [static template library](/guide/pipeline-prompts.html) remains available. Maintained static data: `config/glance/pipeline-prompts.json`; render with `scripts/render-pipeline-prompts.py`.

Validation on 20 October 2026: 27 real skill contracts, 28 skill files, seven prompt-model tests and 14 layout tests passed. Full lint/type checks passed. Candidate and published browser tests verified defaults, dimensions, copy/fallback, stale-output clearing, pipeline-specific questions and mobile width without submitting session work. Admission, memory, exact-image rollback and runtime tool checks passed. Production source a007c71a780394ea1e32f33e5ea91ec449d3cf95; evidence /data/ai/helper-scripts/reports/prompt-builder-20261020.

Dropdown visibility fix (20 October 2026): native fields and popup options use matching opaque v2 theme colours in light and dark modes. Empty startup skill discovery is retried briefly; loading errors stay on the page with Retry. Refresh an existing tab after the update. Eight model tests, full lint/type checks, exact-image rollback, and published browser checks for all 27 pipelines, themes and clipboard passed. Source 5ed2469dfbb53fd56108080d3feea154b3ce1ffe; evidence `/data/ai/helper-scripts/reports/prompt-colour-20261020`.

## Image prompt safe default (2026-10-21)

The image pipeline previously left its required model field blank, silently
leaving Build prompt disabled for users who did not know an installed model ID.
It now supplies an editable discovery instruction: choose a compatible existing
installed model, verify any LoRA base, ask before downloads/installations, and
report a blocker if none is available. Prompt building itself starts no job.
Refresh an already-open builder and Prepare questions again (or reset to safe
defaults) to receive the updated field. Existing typed model IDs remain usable.

Reproduced and verified against the production page, including actual prompt
output, clipboard equality, light/dark dropdowns, mobile layout, and absence of
session/job submissions. Security authorization still has no fabricated default.
Evidence: `/data/ai/helper-scripts/reports/prompt-build-button-20261021/`.

## Build action and workspace destinations (2026-10-21)

The image form rejected `/workspace/images` even though `/workspace` is the
application's persistent mounted workspace. The resulting validation message
was below the visible form, leaving an empty preview that looked unresponsive.
The builder now accepts `/workspace` and contained project destinations, while
rejecting traversal and unrelated roots. These are container paths; `/workspace`
is mounted from `/data/ai/watoom-code/workspace`, not `/data/ai/projects`.
Prompt instructions do not grant filesystem or execution privileges.

Build remains clickable so missing required fields produce a focused, marked
input and visible validation. Invalid project paths focus the project input;
success focuses and reveals the preview and displays a ready status. Existing
required authorization stays empty and cannot produce a valid prompt by default.
Tests cover `/workspace/images`, invalid paths, missing authorization, mobile
preview visibility and clipboard, without submitting any work.

Application source: `1392405afa11fedd2d94bf0fba5142165eaad452`.
Image: `127.0.0.1:5000/watoom-code@sha256:d6d3a2f20de631475d36c9bafb4e9f189c320c43274c0c92f03951e80795c261`.
Evidence: `/data/ai/helper-scripts/reports/prompt-action-20261021/`.

## Canonical image folders and cached tabs (2026-10-21)

Named folders anywhere under `/data/ai/projects/` are valid prompt destinations,
including `/data/ai/projects/images` and nested image revisions. The earlier
fixed games/development/pipelines whitelist was too restrictive. Traversal and
unrelated filesystem roots remain rejected. Both canonical images and the
container's `/workspace/images` destination are covered by browser regression.

The web service worker intentionally pins open tabs to one complete build:
`skipWaiting=false`, `clientsClaim=false`. An ordinary refresh may keep the old
interface while older clients remain open. Save unsaved entries and close all
OpenCode tabs/windows before reopening; a private/incognito window loads a fresh
interface without deleting the original browser's storage. Do not override this
protection or mix lazy assets from different releases to force an update.

The initially cold isolated catalog failure was retained. Browser acceptance
was rerun after the native skill catalog reported its 112 registered skills.
Production promotion still requires exact-image browser/runtime/rollback gates.
A user-authorized active-session pause was required for the UI rollout; session
history/files were preserved and task content was not changed.

Source: `cf92b54c43811f492fdf04c00bf151d95a182878`.
Evidence: `/data/ai/helper-scripts/reports/prompt-path-20261021/`.

Update 6 November 2026: added `game-template` (genre template catalogue), `game-blueprint` (design interview and milestone plan) and `terrain-map` (real-world terrain to Godot). The template catalogue gained nine pinned, licence-checked genre templates (platformer, metroidvania, deckbuilder, tower defense, RTS, top-down shooter, starter, racing, souls-like); 19 in total. The browser test needs Playwright, which is not installed on the operator host, so it was not rerun; the static page render and skill block parsing passed.
