---
name: ansible
description: Use for Ansible roles, playbooks, inventories, variables, AAP automation, ansible-lint, syntax checks, and idempotent infrastructure changes.
---

# Ansible

## Rules

- Preserve idempotency.
- Use FQCNs.
- Prefer modules over `shell`/`command`.
- Inspect role defaults, vars, argument specs, handlers, and existing conventions before adding structure.
- Do not invent variables or duplicate an existing abstraction.
- Keep secrets out of output and source.

## Validate

1. syntax check;
2. repository-configured `ansible-lint`;
3. `--check --diff` when safe and meaningful;
4. targeted execution only when requested/appropriate.

## WatooM conventions

When working in the WatooM repository:

- Active project: `/data/github/watoom-standardised-homelab/standardised_k3s_project`.
- Run Ansible from the project's `ansible/` directory unless the existing workflow says otherwise.
- Prefer existing roles/playbooks over parallel installers.
- Package changes for Kali/OpenCode/etc. belong in the owning role/IaC.
- Preserve dirty unrelated changes and never stage automatically.
