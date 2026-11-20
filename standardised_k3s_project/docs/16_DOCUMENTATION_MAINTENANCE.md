# Documentation Maintenance

## Sources and outputs

The browser guide at `https://glance.internal.homelab.example/guide/` is generated. Edit the sources:

| Output (`config/glance/guide/`) | Source | Renderer |
|---|---|---|
| `index.html`, `<page>.html`, `assets/search-index.json`, redirects (`ansible-iac.html`, `llm-*.html`) | `docs/guide/*.md` | `scripts/render-glance-guide.py` |
| `software-design.html` (cross-project integration SDD; repo pointer `docs/SOFTWARE_DESIGN.md`) | `docs/guide/software-design.md` | `scripts/render-glance-guide.py` |
| `assets/llm-platform/*` reference downloads | `docs/llm-platform/api`, `examples`, `verification.json` | `scripts/render-glance-guide.py` |
| `job-reference.html` | `config/glance/job-reference.json` | `scripts/render-job-reference.py` |
| `pipeline-prompts.html` | `config/glance/pipeline-prompts.json` | `scripts/render-pipeline-prompts.py` |
| `padkontrol-v18.html` | hand-maintained | — |
| Glance dashboard Knowledge page | skill registry catalogue | `scripts/render-glance-knowledge.py --catalog <registry.sqlite3>` |
| Glance ConfigMaps (`manifests/10-infrastructure/glance/glance.yml`) | `config/glance/glance.yml`, `config/glance/helper.py` | `scripts/render-glance-configmaps.py` |

Guide pages describe current state only: no dated history, evidence trails or superseded environments. Record evidence in `.opencode/work/` and artifacts, not in the guide.

## Writing a guide page

Each `docs/guide/<page>.md` starts with front matter:

```text
---
title: Page title
nav: Sidebar label
summary: One or two sentences shown under the title and in search.
---
```

- Use `##` and below; the title is the page's h1. `##` sections are numbered and appear in the sidebar contents.
- Link other pages as `network.md` or `network.md#public-exposure`; the renderer rewrites and validates them, and fails on a missing page or anchor.
- Callouts: a blockquote starting with `[!NOTE]`, `[!RULE]` or `[!WARNING]`.
- Raw HTML is disabled. Tables and fenced code (with copy buttons) are supported.
- A new page must be added to `PAGES` in the renderer; an unlisted source fails the render.

## Theme

`config/glance/guide/assets/site.css` holds every colour and font token. Page stylesheets (`job-reference.css`, `pipeline-prompts.css`) use those tokens. The Glance dashboard `theme:` HSL values and its `document.head` style layer match the same palette.

## Render and validate

```bash
/data/ai/toolchains/docs-render/bin/python scripts/render-glance-guide.py          # write
/data/ai/toolchains/docs-render/bin/python scripts/render-glance-guide.py --check  # drift
python3 scripts/render-job-reference.py --check
python3 scripts/render-pipeline-prompts.py --check
python3 scripts/verify-homelab-documentation.py   # local links, anchors, duplicate IDs, dashboard links
python3 docs/llm-platform/validate.py              # pinned schemas, refs and client request shapes
```

The `docs-render` environment provides `markdown-it-py`; do not install it into application Python environments.

## Publication

Glance mounts `config/glance/guide` from the operator checkout (`/data/github/watoom-standardised-homelab`) at `/app/guide` by hostPath. Guide HTML is live as soon as that checkout updates; no restart is needed.

Dashboard changes (`glance.yml`, `helper.py`) need the ConfigMaps rendered, applied and a Glance rollout. When dashboard links point at new guide pages, publish the guide first.

Old single-page anchors (`/guide/#<anchor>`) are forwarded to their new page by `assets/site.js` (`LEGACY` map). Keep that map when renaming sections that external bookmarks may use.

## 5 November 2026 — picker, learning loop and Blender v3.2

Updated `docs/guide/watoom-code.md`, `docs/guide/games.md`, the platform overview and unified Blender operations reference for the six config-driven project spaces, harness verification, off-by-default nightly sidecar curator and all three rollback levers, and the v3.2-godot-path runtime receipt fix. The learning summary points to the existing design, sections 3 and 6; deployment and durable-change approval gates remain explicit.

Regenerate HTML and `assets/search-index.json` with the existing `scripts/render-glance-guide.py`; validate render drift, documentation links and the exact changeset through phase 2. Markdown/HTML are skipped by phase 2, so its JSON grader verdict supplements the renderer/link checks. Evidence and integration outcome are recorded under `.opencode/work/glance-docs-update/progress.md`. This documentation task does not deploy, change image pins or enable the curator.

## Server source catalogue and private distribution

`python3 scripts/render-server-catalogue.py` generates `docs/server-catalogue.json`
and the `server-catalogue`, `server-scripts`, `server-playbooks`, `server-roles` and
`server-tools` guide Markdown from tracked `scripts/`, `ansible/playbooks/`,
`ansible/roles/` and `tools/` source. Run it before `render-glance-guide.py` and run
both with `--check` after generation. The guide renderer copies the complete JSON
to `/guide/assets/server-catalogue.json`; new reference pages are registered in
PAGES/GROUPS and use the existing theme, search and navigation.

The curated `llm-project`, `llm-extensions` and `llm-publication` pages supply
project-level documentation. Keep them and the cross-project SDD in sync when an
extension owner or distribution source changes. Do not present static extraction as
proof of runtime installation. Private-source bodies are excluded from descriptions.

## Environment recovery documentation

`docs/guide/disaster-recovery.md` describes the executable recovery helper in
`tools/recovery/`, the scope/stages in `config/recovery/policy.json`, private
capture/off-host/restore evidence and replacement-host safeguards. The source
inventory in publication metadata is sanitised; private captures, restore scratch,
credentials and service data must never enter Git. Regenerate catalogue and guide
outputs after changing a recovery entrypoint or deployment source. A readiness
blocker is preserved until real supporting evidence is available.
