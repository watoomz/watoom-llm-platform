# Validation and Change Control

## Ansible validation tiers

| Tier | Required checks | Use |
|---|---|---|
| `fast` | YAML + production-profile `ansible-lint` + WatooM policy | quick/local and LLM repair loop |
| `standard` | fast + syntax validation in configured production EE | production AAP-targeted content |
| `full` | standard + configured safe dynamic/idempotence hook | highest-assurance change |

```bash
./scripts/watoom-ansible-validate.sh fast
./scripts/watoom-ansible-validate.sh standard
./scripts/watoom-ansible-validate.sh full
```

Required validation that cannot run is **not a PASS**.

## Policy themes

The custom policy covers:

- literal/sensitive secret handling
- `no_log`/diff safety
- TLS validation and credential transport
- external download integrity
- AAP/runtime portability
- idempotency and command/shell outcome semantics
- handler/restart discipline
- delegated write concurrency
- anti-bypass/security-policy downgrade attempts

## Production acceptance

A change is not complete solely because `kubectl apply` or Ansible returned zero failures. Check:

- host network/default route
- k3s node Ready
- required Secrets exist (without displaying values)
- no unexpected failed/pending pods
- Docker stacks expected to run are running
- Glance/Grafana health
- application-specific smoke tests

## Production fixes belong in the build

The accepted WatooM Code/Toolkit/Unreal release is production. Correct defects in authoritative source and normal IaC/build configuration, add or update the affected regression checks, publish versioned artifacts, validate through the established guarded promotion, and update current documentation. A one-off repair or report path must not become a hidden dependency of the final build.

Select validation for the actual change. Documentation-only updates need renderer/link/served-content checks; they do not require model reloads, GPU swaps, an application restart or a repeat of unrelated acceptance. Runtime changes need relevant real behavior and rollback evidence. Preserve active work and standing approval gates.

The stable WatooM Code Swift context is 100000, with 4096 output. Keep it distinct from the backend's 131072-token capacity. The Model Manager is deployed and real GGUF generation passed. Image/LoRA acceptance is tracked separately; fixture success never qualifies actual inference.

## Git discipline

```bash
git status --short --untracked-files=all
git diff --check
git diff -- <changed-paths>
```

Do not use broad `git restore`, `reset`, `checkout`, `clean` or stash operations to isolate one fix on a working tree with other approved changes.

## Image governance

Use the image audit/export workflow to capture known-good live digests and detect floating references. The live image lock is a diagnostic and pinning aid; update it from verified running state rather than hand-editing historical values.

## Kali security isolation

Only `watoom-kali` can use the Kali MCP tools. Check the live rules with `python3 scripts/verify-opencode-kali-security.py`; details in Kali security workflow.
