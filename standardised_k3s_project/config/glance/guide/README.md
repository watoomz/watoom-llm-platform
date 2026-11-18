# Glance guide (generated output)

Served at `https://glance.internal.homelab.example/guide/` from the operator checkout by hostPath
(`/app/guide` in the Glance pod). Edit the sources, not the HTML:

| Output | Source | Renderer |
|---|---|---|
| `index.html`, `<page>.html`, `assets/search-index.json` | `docs/guide/*.md` | `scripts/render-glance-guide.py` |
| `job-reference.html` | `config/glance/job-reference.json` | `scripts/render-job-reference.py` |
| `pipeline-prompts.html` | `config/glance/pipeline-prompts.json` | `scripts/render-pipeline-prompts.py` |
| `padkontrol-v18.html` | hand-maintained | — |

Theme: `assets/site.css` holds every colour token; page stylesheets use those tokens.

```bash
/data/ai/toolchains/docs-render/bin/python scripts/render-glance-guide.py --check
python3 scripts/render-job-reference.py --check
python3 scripts/render-pipeline-prompts.py --check
```
