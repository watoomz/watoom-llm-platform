# Illustration, lettering and delivery

Read comics-script.md for the story and panel plan. Use the selected genre,
audience, art style, reading direction and production format; do not assume a
superhero look, manga direction, color palette or realism level.

## From thumbnail to final page

1. Thumbnail the sequence in tiny rough pages/spreads. Include placeholder
   balloons and captions immediately. Test reading route, silhouettes,
   geography, emotional beats and page turns with cheap revisions.
2. Develop layouts/blue pencils: panel boundaries, camera placement, character
   blocking, perspective and balloon zones. Blue is a convention, not a
   required color or software feature.
3. Refine pencils: anatomy appropriate to the style, expressions, gestures,
   props and architecture. Use the visual bible and legitimate references.
4. Ink or finalize linework: purposeful line-weight hierarchy, readable blacks,
   foreground/background separation and consistent detail density.
5. Color, grayscale or screentone as selected. Maintain scene palettes, value
   separation and light continuity; color should support mood and action.
6. Finish lettering and SFX on separate editable layers when possible. Preserve
   the exact approved text, order, speaker identity, punctuation and special
   delivery. Check diacritics, missing words, balloon padding, tails, contrast,
   tangencies, and effects that obscure essential art.
7. Review at thumbnail, intended print/screen size and enlarged detail. Inspect
   actual pages, not only file names, prompts or scripts. Fix sequence-level
   problems before polishing individual images.

These are useful production stages, not a requirement to redo finished work.
A digital painter may combine stages. Keep versioned source/layers and export
copies rather than flattening the only editable master.

## Persistent notes to illustrations

Use graphic-novel-art-notes.md while co-writing. Each page has durable art notes
and links to its planned assets in illustration-manifest.json. On a later
request to illustrate the book, chapter or page range, load those files plus the
current script and visual bible. Reuse approved scene details instead of asking
the user to describe the images again. Resolve stale or incomplete notes before
preparing that batch. The manifest is a project planning record, not a new queue
API or automatic rendering daemon.

After the exact batch is approved under the existing image workflow, submit all
its distinct planned images once with stable request ids, then yield for the
existing native worker. Reconcile receipts back to the manifest and per-page
notes when resumed. Do not confuse generation with page assembly, lettering,
visual review or a completed graphic novel.

## Illustration briefs and native image tools

Give each page/panel a stable id and include characters/wardrobe/reference ids,
shot, pose/action, emotional intent, setting/props, light/palette, composition,
continuity, aspect/pixel budget and reserved lettering areas. Separate exact
dialogue from the visual prompt. Describe visual properties concretely; ask for
references only when identity or an existing look cannot otherwise be preserved.

If actual images are requested, load the installed watoom-prompt-image and
watoom-explicit-image-creator skills. Inspect the currently available native
image tools/models and their limits. Follow their existing reviewed preview/
Generate and stable-id queue/receipt lifecycle; never invent an image tool,
install a renderer or change the GPU/model directly. Do not auto-generate a
whole book from a script request. If only writing is available, deliver the
script and illustration briefs and report that art has not been rendered.

Use consistent character/location references and panel-specific prompts; a seed
alone does not prove identity continuity. Mark a whole-page concept as a concept
until panel geometry, text and continuity have been inspected. Prefer separate
editable lettering to unreliable generated text. An illustration prompt cannot
guarantee exact print dimensions, anatomy, text or panel ordering; verify output
pixels and inspect actual art, revising authorized work as needed.

## Accessible reading edition

Provide a reading-order transcript with page/panel ids, speaker names, captions,
dialogue and relevant SFX. Add descriptions for visual actions, setting changes,
emotions, significant lettering and layout devices that carry narrative meaning.
Separate visual description from quoted dialogue; do not invent motives or
unseen actions. Avoid needlessly duplicating the transcript in every alt text.

Group a continuous action across panels when that reads more naturally, while
preserving panel anchors and sequence. Describe exact spatial arrangement when
it matters to understanding. Convey significant shifts in time and visual
metaphors; avoid interrupting an intense exchange with irrelevant inventory.
Do not reveal a later visual twist earlier than a sighted reader encounters it.
Keep tone consistent with the work. Identify descriptions/transcript as supplied
content, not proof that an exported PDF/EPUB is accessible: verify its tagging,
reading order and text extraction with the relevant format workflow.

## Print and digital checks

For print, use at least 300 pixels per inch at final physical size for color/
continuous-tone pages, and target at least 600 for raster line art. Keep vector
lettering/lines vector where supported. Confirm the selected printer's actual
specification before final delivery: trim, bleed, safe area, binding/gutter,
color profile, black handling and PDF standard vary. Do not silently apply a
generic bleed value or convert everything to CMYK without the printer's profile.

Pixels = inches multiplied by target PPI, calculated for the full canvas
including any required bleed. Example: a 6 by 9 inch trim is 1800 by 2700 pixels
at 300 PPI before bleed. Merely changing a DPI metadata tag or upscaling a small
image does not restore missing detail or prove print quality.

Check every page's real dimensions, effective PPI, crop/bleed/safe zones,
embedded licensed fonts, text legibility and page/spread ordering. Use the
installed document/PDF workflow if actually exporting those formats. Screen
editions need appropriate pixel sizes/compression and tested mobile legibility,
rather than a print-DPI claim. Keep the layered master separate from exports.

Finish with delivered page range, stage, source/export files, reviewed artifacts
and outstanding issues. Final art, visual acceptance and print readiness are
separate claims requiring their respective checks.
