# Persistent illustration notebook and notes-to-images workflow

The author co-writes the story with the model. The model records what must be
illustrated on every page as it writes, then uses that saved production notebook
when asked to create the images. This is an extension of the existing native
writing/image workflow, not a new service or permission to generate unsolicited
images.

## Project files

Resolve comic-root to adaptations/comics/ inside a story-project adaptation,
comics/ inside a standalone original, or the author's existing comic folder.

- comic-root/script/: current scripts, or link the existing issue/chapter files.
- comic-root/visual-bible.md: established character/location/wardrobe/style ids.
- comic-root/art-notes/<page-id>.md: one persistent illustration note per page.
- comic-root/illustration-manifest.json: planned assets and generation progress.
- comic-root/art/<page-id>/<asset-id>/<revision>/: copied verified images and
  receipts, preserving earlier revisions. Use the existing verified publication
  route when copying generated output.
- Existing .opencode/work/image-creator/ stores native image drafts/approval
  revisions as required by the installed image-creator skills; link them from
  the manifest instead of creating a competing prompt approval system.

Use stable logical page, panel and asset ids. Display page numbers can change;
reordering pages should update display/order fields and continuity links, not
silently reassign an old asset's identity to a different story moment.

## Maintain notes during co-writing

At the end of each writing/editing chunk:
1. Save the current script. For each drafted page record the visual information
   needed to understand its story beats. Every panel needs a drawable moment,
   even a silent reaction, an establishing view or a meaningful visual clue.
2. Update its page-art note with source file, exact revision/hash when available,
   scene ids, visual-bible revision and continuity entering/leaving the page.
   Never invent a checksum. Preserve approved text and author choices.
3. List the exact required image assets, their intended use, and whether the
   target is separate panel illustrations, one full-page image, or a spread.
   Page count does not automatically equal image count. Distinguish an
   illustration from the later composite/lettered page.
4. Update illustration-manifest.json. DRAFT means unresolved notes; READY means
   complete enough for a generation preview, not approval to render.
5. Reconcile all drafted pages against the note files. Report a missing note
   rather than claiming the notebook is complete. Keep updates in the writing
   task; do not ask the author to repeat the story as an image description.

Capture what must be depicted and why: narrative purpose; setting/time/weather;
characters and exact wardrobe/injury/prop state; visible action/pose/expression;
shot/staging/eyelines; clues and essential details; palette/light; text zones;
reading order and any reveal that must not be shown early. Explain what to avoid
only when it is an established requirement; do not invent exclusions or silently
change a supplied negative prompt.

## Example page-art note

---
type: comic-page-art
page-id: page-001
display-page: 1
script: ../script/chapter-01.md
script-revision: draft-03
note-revision: note-01
visual-bible-revision: bible-02
status: READY
---

Story purpose: Kai discovers the tower signal has failed.
Context before: Kai is alone on tower-top at night in the same storm.
Context after: Kai decides to investigate; the light below is not yet revealed.
Continuity: keeper-kai; coat-v1 remains intact; lamp-v1 changes from lit to dark.
Page layout: three panels; left-to-right; caption reserve in panel 1 sky.

Panel page-001-panel-01 / asset page-001-panel-01-art:
Wide: tower against rough dark water; lit lantern; Kai small at the window.
Mood: routine and isolation. Preserve the tower silhouette from tower-top-v1.
Lettering, separate: CAPTION 1, “One light meant home.”

Panel page-001-panel-02 / asset page-001-panel-02-art:
Close: the same lamp housing, now dark. No second light or added figure.
Lettering, separate: SFX 2, “tik”.

Panel page-001-panel-03 / asset page-001-panel-03-art:
Medium: Kai holding the dead lamp, concerned but beginning to act.
Keep coat, face and lamp consistent; reserve balloon space above the shoulder.
Lettering, separate: KAI 3, “That should not be possible.”

Production: separate panel art; editable lettering/page assembly remains pending.
Generation drafts/receipts: none yet.

This example is documentation. Real notes must describe the actual story, not
reuse the lighthouse scene or these character defaults.

## Manifest contract (project record, not native tool arguments)

Use a JSON object with schema "watoom.comic-illustration-plan.v1", project,
visual_bible, pages (ordered page ids and note/script paths/revisions), assets,
and batches. Keep paths project-relative except real backend receipt pointers.
Each asset records:
- id, page_id, panel_ids, purpose/output_kind, note_revision, script_revision
  and visual_bible_revision;
- status, approved_draft_path/preview_hash when present, pinned installed model
  id/revision/settings once discovered, and exact native prompt/negative;
- request_id only when a specific approved generation revision is prepared;
- output_path, receipt_path, checksum and actual settings only from real results;
- review state, failure reason, dependency ids and superseded revision if any.

Supported planning states: DRAFT, READY, APPROVED, SUBMITTED, GENERATED,
REVIEW_PENDING, ACCEPTED, STALE, FAILED, UNCERTAIN. Review and generation are
distinct: successful bytes/receipt do not prove visually acceptable artwork.
A batch records its exact asset/revision list, draft/preview reference, approved
scope and request/receipt state. This is bookkeeping around the installed
image-creator approval helper, not a substitute for that helper.

## Later: create images from the notebook

When the author asks to illustrate a chapter/page range/book:
- Read the current scripts, relevant page-art notes, bible and manifest. Select
  exactly the requested scope; count assets rather than assuming one per page.
  Reuse existing accepted/submitted images and list remaining assets. Resolve
  missing references, conflicting notes or stale revisions before submission.
- Use watoom-prompt-image and watoom-explicit-image-creator. Populate their
  reviewed prompts and settings from the notes. Keep each panel's unique scene;
  do not replace every panel prompt with a generic common style block.
- Present the concrete final batch through the existing Generate workflow:
  image count, page/panel ids, positive/negative text and model/settings. The
  author can approve a complete batch once; do not add approval per image after
  that. Writing approval and READY notes alone do not authorize GPU work.
- Once the exact batch is approved, queue all its distinct assets once through
  the existing native tools with stable request ids and pinned model revisions,
  recording each accepted submission immediately. End the turn after submission
  so the native idle/GPU handoff can operate; no polling loop, new daemon,
  auto-session creation, direct inference or chat-model preemption.
- On native completion/resume, reconcile real receipts and copy published
  outputs via the established verified route. Update the manifest and page note
  with actual files/settings/checksums. Inspect pixels using an available vision
  tool/model before marking ACCEPTED. A text-only model must leave REVIEW_PENDING.
- Assemble pages and add exact lettering only using available inspected tools.
  Otherwise retain the panel illustrations and mark composition/lettering
  pending; a folder of generated panels is not a finished graphic novel.

If reference-image conditioning is unsupported, retain the references as art
direction but state that they cannot be passed as model conditioning. Never
promise exact character continuity from prompts or seeds alone.

## Revisions, interruption and failures

A story/bible/layout edit changes the required artwork: revise affected notes,
mark dependent outputs STALE, and invalidate only affected preview approvals.
Preserve unaffected accepted assets and earlier versions. Do not regenerate an
entire book because one expression changed.

A SUBMITTED asset with an uncertain response becomes UNCERTAIN; query/reconcile
the original request id. Never replay it with a fresh id. Record a real FAILED
receipt and reason; preserve successful assets. A revised retry is a new
versioned asset revision and follows existing authorization rules. Resume from
the manifest, native drafts and receipts rather than conversation memory.

Report the page-note coverage, requested asset count, submitted/generated/
accepted counts, stale/failed/uncertain assets, and pending page assembly.
Never say images were created when only notes/prompts were saved.
