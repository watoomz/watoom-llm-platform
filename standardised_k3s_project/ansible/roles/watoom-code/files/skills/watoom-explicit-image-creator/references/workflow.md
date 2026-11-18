# Shared wizard operation

This helper is the same for both image skills. It builds prompts and request plans; only the actual native image tool can render. All examples are non-graphic fictional art.

The assistant supplies scene analysis and optional polished prose; the helper does not pretend to extract semantic fields from text. Populate only grounded details, and distinguish suggested tags. Supported detail fields are in `assets/fields.json`.

Example initial JSON:

```json
{
  "idea": "An adult adventurer reading a map in a candlelit library, painterly",
  "analysis": {
    "human": true,
    "description": "An adult adventurer studies a map in a candlelit library, rendered as a painterly illustration.",
    "tags": ["solo", "library", "candlelight", "map"],
    "details": {
      "subject": {"number": "one", "age": "adult"},
      "pose": {"action": "reading a map"},
      "environment": {"location": "library"},
      "lighting": {"source": "candles"},
      "art_style": {"type": "painterly"}
    }
  }
}
```

Run only from an execution-authorized coordinator/builder, using paths in the selected project. `/config/skills/watoom-explicit-image-creator/scripts/wizard.py` is the installed app helper. The corresponding host path is `/data/ai/watoom-code/config/skills/watoom-explicit-image-creator/scripts/wizard.py`.

```sh
python3 /config/skills/watoom-explicit-image-creator/scripts/wizard.py new --state /selected/project/.opencode/work/image-creator/draft-001.json --input /selected/project/.opencode/work/image-creator/idea.json --preferences /config/preferences/watoom-explicit-image-creator.json
```

`apply --state <draft> --input <action.json>` accepts these actions:

| Action | Data | Result |
|---|---|---|
| `edit_positive` | `description`, `tags` | Return to positive review; approvals invalidated |
| `approve_positive` | `{}` | Suggest negative; enter negative review |
| `edit_negative` | `{"text":"exact exclusions"}` | Preserve exact negative text and require review |
| `approve_negative` | `{}` | Enter optional additional details |
| `details` | Category objects with field/value pairs | Prefill/update only chosen details |
| `continue` | `{}` | Skip/finish optional questions and enter final review |
| `edit_settings` | Any supported sampling fields | Invalidate displayed final preview |
| `select_model` | Exact catalog entry plus internal checked `prompt_profile` evidence if available | Require prompt reapproval for changed conventions |
| `apply_preset` | `{"name":"preset-name"}` | Apply saved defaults without overwriting explicit filled fields; re-review |
| `save_prompts` | `{}` | Prompt-only export state; no renderer involved |
| `generate` | `preview_id` and freshly checked `current_model` | Build one stable native request plan only |
| `record_receipt` | `request_id`, `job_id`, `receipt` | Retain actual backend receipt under that revision |
| `refine` | Changed `description` and/or `tags` | Preserve prior prompts/settings; start a new review revision |

An action file has `{"action":"approve_positive","data":{}}`. The helper checks phases and rejects skipped reviews. `preview --state <draft>` emits approved positive/negative, checkpoint, settings, aspect ratio and unsupported controls, with a hash of the exact preview. The user must choose Generate for that preview. A stale hash, missing/stale installed model, incompatible score tags or unsupported sampling values fails. `request_plan` is ready-to-review JSON for `watoom-images_submit_image`, not evidence of a submitted job. The helper never sends it.

Internal model annotations use this shape only after actual revision-scoped documentation has been checked:

```json
{"prompt_profile":{"family":"pony","verified":true,"revision":"exact-catalog-revision","source":"pinned model-card URL or local metadata path plus checked evidence"}}
```

The catalog itself does not supply this annotation. Do not invent it or infer it from names. Without verified evidence, omit it and use natural-language-first unknown-profile prompting. `sdxl` also requires documented identification to label the profile; no automatic Pony tags are inherited. The profile fixtures test conditional behavior and do not certify installed models.

Save a preference/preset only at the user's request. `preset --preferences /config/preferences/watoom-explicit-image-creator.json --name warm-library --input <values.json>` writes a private atomic file without a model call. Values may include `default_human_appearance`, `style_preset`, `positive_tags`, `negative_tags`, `camera`, `lighting` and supported `generation_settings`. Reopen the file in another session to load these defaults. Request values and established references win over defaults. Saving a preset is separate from applying it; it does not grant generation approval.

Refinement example: after the previous image, "Make the lighting warmer" changes only the lighting fields and the corresponding descriptive text/tags, retains pose/model/seed/camera, and returns to prompt review. The original image and its raw backend receipt stay unchanged. Do not promise identical people when the backend only exposes text and seed.
