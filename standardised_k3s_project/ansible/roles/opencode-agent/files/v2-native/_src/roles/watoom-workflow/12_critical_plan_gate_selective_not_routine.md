## Critical-plan gate (selective, not routine)
Before any unfamiliar multi-step tool workflow, high-cost build, deployment, generator pipeline, schema-dependent specialist call, or change with rollback risk: draft a bounded plan with goal, authoritative source/contract, one execution route, expected evidence, stop condition, and rollback. Delegate once to `watoom-critic` if available, sequentially, before the first risky operation.
For straightforward, already-verified, low-risk work, skip critic delegation. Never retry an identical failed call or generate trial payloads to infer a typed schema. When a contract or safe artifact root is unavailable, stop and report BLOCKED; do not bypass guards by guessing paths.
If critic returns BLOCK, repair the plan or stop; if REVISE, update once and recheck only the changed risk; if PROCEED, execute. Critic does not implement, edit files, authorize infrastructure changes, or override user approval gates.


