# Skill and job reference — 25 October 2026

Glance serves `/guide/job-reference.html`:130 installed skills and27 maintained pipeline templates, with example requests, inputs, scope, search, category/type filters and clipboard fallback. Native discovery and pipeline contracts were checked on25 October2026 (Australia/Brisbane). Installed guidance, prompt preparation and verified execution are distinct.

Maintain `config/glance/job-reference.json` when skills or pipelines change. Reconcile with `/api/skill?directory=/workspace` and `config/glance/pipeline-prompts.json`; review examples rather than publishing private instruction bodies. Regenerate with `python3 scripts/render-job-reference.py` and validate with `--check`. Guide and pipeline-template navigation link to the page. Existing hostPath publication needs no service restart.

Validate inventory coverage, escaped content, links, search/filter/copy behavior, mobile layout and served hashes. The page prepares text only; it never submits jobs, obtains credentials or invokes workers. Per-asset and runtime acceptance need independent evidence.
