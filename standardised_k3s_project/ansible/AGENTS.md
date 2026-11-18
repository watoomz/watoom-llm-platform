# WatooM Ansible Rules

These rules apply under `standardised_k3s_project/ansible/`.

## Execution

Run Ansible from this directory.

Syntax check:

```bash
ansible-playbook -i inventories/homelab playbooks/<playbook>.yml --syntax-check
```

Deployment:

```bash
ansible-playbook -i inventories/homelab playbooks/<playbook>.yml
```

## Conventions

- Keep roles and playbooks idempotent.
- Prefer Ansible modules/templates over imperative shell commands.
- If `command` or `shell` is necessary, make change detection explicit where practical.
- Put persistent settings in role defaults, vars, group vars, templates, or established config sources.
- Inspect existing roles before creating a new role or helper mechanism.
- Reuse existing variable names and project conventions when appropriate.
- Do not hard-code host-specific or environment-specific values in role logic when an established variable/config mechanism exists.
- Use the existing secret-management pattern already present in the repository; do not invent a parallel secret system.
- Never place credentials, tokens, private keys, or passwords in plaintext committed source.

## Validation

For a normal change:

1. inspect the targeted diff;
2. run `git diff --check`;
3. run the affected playbook's `--syntax-check`;
4. deploy only the affected playbook/role;
5. wait for relevant Kubernetes rollout where applicable;
6. verify the live state;
7. confirm the Git index is unchanged unless staging was explicitly requested.

Use `ansible-lint` when it is already available/configured for the affected area; do not add new tooling just to satisfy this rule.

## Boundaries

- Do not run broad/unrelated playbooks just to validate a small change.
- Do not add a second package-management path when an existing helper/role already owns packages.
- Do not change network infrastructure unless explicitly requested.
- Do not broaden privilege, authentication, or authorization to make deployment easier.
