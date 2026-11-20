# Writing Studio

A web page for creative writing and graphic-novel art (T-0099), at `https://glance.internal.homelab.example/writing/`
(Glance → Create → Writing Studio). Stdlib-only Python, same shape as `tools/creation-studio`: a host service bound
to the k3s cni0 bridge, a Glance IngressRoute, one self-contained page, and offline tests with fakes. It owns no
generation backend.

## What it does

- **25 creative-writing skills** in a sidebar, grouped Start / Plan & build / Write / Revise & review / Publish /
  Verse & prompts. Picking a skill shows either a **form** (fields that fit the skill, e.g. *Write a chapter*: story so
  far, beats, voice, length) or a **chat** (discussion-style skills: *Creative writing* router, *Premise workshop*,
  *Discovery drafting*, *Theme*, *Self-publishing*). Fields, chats and the last skill are kept in the browser.
- The system prompt is the skill's own **SKILL.md** (copied from `ansible/roles/watoom-code/files/skills/<skill>/` by
  the role, so the studio and WatooM Code share one source) behind a short preamble: the page has no tools or files, so
  the model writes the content directly instead of running the skill's scripts.
- **Model switch and warm-up**: the header lists the router's language models (not LLaMA-Mesh or the GLB coder) and
  what is loaded now. *Warm up* asks the router to load the chosen model (`POST /models/load`; the router asks the GPU
  controller, minutes from cold) so the first request starts at once. The default is the primary model, so nothing
  switches unless you choose another one. *Thinking* turns the model's reasoning on for a request.
- Answers **stream server-side** (one job at a time) and survive page reloads; the page polls `api/job`. Finished
  jobs are kept in `--output-dir` (`.md` + `.json`) and listed under *Recent writing*; *Download .md*, *Copy* and
  *Use as art scene* act on the result.
- **Graphic-novel art** goes to MOSS Image Studio's existing API through an allow-list (status, config, generate,
  job status/cancel, image, session start/end). Seven comic styles wrap the scene (ink noir, ligne claire, modern US,
  manga, watercolour, painted, golden-age) with a no-lettering negative prompt, page/panel/splash sizes, and **50
  steps** by default (MOSS allows up to 60). MOSS has no model switch; it needs its own GPU session (*Start GPU session*
  pauses the language model until *End session* or 10 idle minutes), exactly as on the MOSS page. MOSS can only take
  the GPU from the primary model (controller `qwen-ready`): after a *Warm up* of another model, *Start GPU session*
  offers to switch back to the primary first instead of failing with "GPU controller is not idle". Measured
  2026-11-20: the first image of a session loads MOSS (~110 s), then a 50-step 832×1216 page takes ~37 s.

## Layout

| Path | What |
| --- | --- |
| `writing_studio_service.py` | the service: skills, router client (models, warm-up, streaming), writing jobs, MOSS proxy |
| `skills.json` | per-skill panel definitions (group, title, form or chat, fields, chat starter) and the art styles/sizes |
| `web/index.html` | the page |
| `tests/test_service.py` | offline tests with a fake router and a fake MOSS; they load the 25 real SKILL.md files |

Run the tests: `python3 -I -m unittest discover -s tools/writing-studio/tests`

## Deploy

Off unless enabled, like creation-studio:

    ansible-playbook -i ansible/inventories/homelab/hosts.yml ansible/playbooks/writing-studio.yml \
      -e writing_studio_enabled=true -e writing_studio_start=true      # run from ansible/
    kubectl apply -f manifests/10-infrastructure/glance/writing-studio-route.yml

The role creates the `writing-studio` user (uid 1014), a pod-subnet-only firewall rule for port 8793, copies the 25
SKILL.md files to `/data/ai/writing-studio/skills/` and keeps results in `/data/ai/writing-studio/output/`. Re-run the
playbook after editing a skill to refresh the copy (the service restarts when a skill changed).

## Safety

POSTs need `Content-Type: application/json`, a same-origin `Origin` (when sent) and at most 256 KiB; skill names, model
ids and job ids are validated; chats are at most 40 turns. Writer text is never interpreted as HTML on the page.
