# Ansible rules
- Preserve role/defaults/vars/group_vars ownership and repository structure.
- Prefer idempotent modules over shell/command and handlers for restart/reload behavior.
- Avoid duplicated sources of truth.
- When command/shell is unavoidable use precise changed_when/failed_when and safe quoting.
- Validate rendered/config syntax before restart when supported and keep check-mode sane where practical.
- Do not create hidden imperative state outside IaC; verify idempotence after functional verification.
