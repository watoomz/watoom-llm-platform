# WatooM LLM platform documentation

Verified baseline: 2026-11-03, Australia/Brisbane.

## Human documentation

- [Project overview, installation and configuration](../guide/llm-project.md)
- [Software design and integration](../guide/software-design.md)
- [Custom plugins, agents, skills and workers](../guide/llm-extensions.md)
- [API and SDK reference](../guide/llm-api.md)
- [User guide](../guide/llm-user-guide.md)
- [Server scripts, playbooks, roles and tools](../guide/server-catalogue.md)
- [Private GitHub distribution and provenance](../guide/llm-publication.md)

These sources render into the existing Glance guide; there is no second docs server.

## Reference files

`api/watoom-code.openapi.json` is an exact snapshot from production app source commit786682b1489e92cba4e4b5a277bd49c565c94e4f. The upstream MIT notice is retained in `api/OPENCODE-LICENSE.txt`. Its experimental schema has empty operation security arrays; deployed native authentication middleware still applies. Operator extensions may not be represented. `api/router.openapi.json` is the maintained router-owned contract subset, not a complete backend API.

`examples/watoom_client.py` and `examples/watoom_client.mjs` are reference adapters, not a separately supported official SDK. Python requires only stdlib; Node uses built-in fetch/Buffer/AbortSignal.timeout. Importing them performs no network activity. The Python script calls only authenticated server info. Mutation examples must be explicitly invoked and never auto-retried after uncertain transport results.

## Validation and publication

From standardised_k3s_project:

```bash
python3 docs/llm-platform/validate.py
python3 -m unittest discover -s docs/llm-platform/examples -p 'test_*.py'
/data/ai/toolchains/docs-render/bin/python scripts/render-glance-guide.py
/data/ai/toolchains/docs-render/bin/python scripts/render-glance-guide.py --check
python3 scripts/verify-homelab-documentation.py
```

Review source/generated diffs and update verification.json after changes. Publish only explicit documentation paths through the normal owner workflow. No credentials, private database/configuration, prompt histories, model weights or recovery grants belong here. Internal topology is intentionally documented; review deployment metadata before publishing to a public audience. Live guide HostPath publication changes documentation only.
