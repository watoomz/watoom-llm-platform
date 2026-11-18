# Contributing

This is a source distribution of the WatooM LLM platform, released under the MIT License (see [LICENSE](LICENSE)). By contributing you agree that your contribution is offered under the same license.

## Where to make changes

- Application/runtime/UI: `application/` and the affected package tests.
- Native plugins/skills/agents: their maintained source in `standardised_k3s_project/ansible/roles/` or `tools/`; see the custom extensions guide.
- Durable deployment/configuration: the owning Ansible role, manifest input or source configuration.
- Documentation: maintained Markdown under `standardised_k3s_project/docs/guide/`, then regenerate the catalogue and Glance pages.

Use a focused branch, preserve unrelated work and identify the owning component before editing. The server's operator checkout remains production IaC authority; this distribution does not automatically deploy changes back to it.

## Review requirements

Explain the concrete problem, resulting behaviour, source/image identities, tests and rollback. Run only checks appropriate to the change. Acceptance, recovery and cutover helpers may mutate live services: never bulk-run them as a test suite. Application root `bun test` is intentionally disabled; use package scripts. Documentation commands are in the README.

Keep credential values, runtime databases, session contents, acquired assets and private recovery grants out of commits and issues. Do not add dependencies without retaining their license notices. Do not weaken guards to make tests pass. Agent work integrates only through the established dev/review workflow; production publication and activation remain operator actions.

For distribution updates, regenerate and inspect the file/provenance manifests and publication review, rather than copying runtime directories or Git object stores.
