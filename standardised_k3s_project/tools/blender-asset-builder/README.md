# WatooM production Blender Asset Builder

Use the existing native builder in https://watoom-code.internal.homelab.example. Practical prompts and verified status are in docs/BLENDER_PRODUCTION_STATUS.md in the authoritative homelab repository and the Blender section of https://glance.internal.homelab.example/guide/.

The maintained native skill is ansible/roles/watoom-code/files/skills/watoom-blender-asset-builder. Its request runner executes inside production builder sessions, under /data/ai/projects/llm/pipelines/blender-asset-builder/<revision>. It uses the existing Toolkit specialist for actual Blender/Godot/Unreal acceptance and the existing AgentMemory service. It does not install a second MCP server or switch inference workloads.

Production execution uses pipeline.py --request, with the installed request-workflow contract. The server operator helper run-watoom-blender.py prints the current entry point, supports a read-only request plan and forwards the existing guarded production rollback. Actual asset execution runs in a native builder session. Old --root, canary installers and historical audit/smoke scripts remain diagnostic artifacts; do not use them to reactivate the retired canary. Source assets, failed versions and old evidence remain preserved.

Deployment and exact scoped rollback use the existing tools/watoom-code/deploy-platform.py coordinator with --i-approve. See the production status document for current immutable pins, evidence, limits and the rollback command. Native skills are persisted through the existing watoom-code Ansible role.
