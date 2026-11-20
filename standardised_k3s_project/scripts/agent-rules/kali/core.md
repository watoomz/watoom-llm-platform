# Kali core rules
- Operate only on an explicitly resolved authorized target/profile; never widen host/CIDR/port/protocol/credential/action scope after failure.
- The model does not create authorization; IaC/policy does.
- Prefer typed capabilities/actions and consult installed-tool plus installed-version reference evidence before argv construction.
- Never invent flags; LOTCE/policy validation is authoritative before execution.
- Keep calls bounded and do not use internet targets unless explicitly authorized.
