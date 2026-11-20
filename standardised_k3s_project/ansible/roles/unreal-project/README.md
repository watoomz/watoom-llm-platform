# Complete-project starters

Use the existing shared Catalog to find the owned complete project. This normal IaC path stages its entire Content namespace, Config (including input), and descriptor into a NEW project. It never modifies the source library or an existing game. It is separate from mesh-oriented world.compose; no new Catalog or MCP is created.

Example, from the repository root:

    ANSIBLE_CONFIG=ansible/ansible.cfg ANSIBLE_ROLES_PATH="$PWD/ansible/roles" ansible-playbook -i ansible/inventories/homelab/hosts.yml -l homelab-host ansible/playbooks/unreal-project.yml -e unreal_project_create=true -e unreal_project_source=/data/ai/assets/fab/hyper-combat-framework-v4-f92bbc40 -e unreal_project_destination=/data/ai/projects/games/my-new-combat-game

Create the parent directory as part of normal project setup first. Existing destinations are refused, including partial failed copies; inspect and explicitly choose recovery rather than overwriting. Only content-only starters are supported. Code/plugin starters require separate acceptance.

The supported profile is OFFLINE. The source's stale BP_GameInstance_Base reference is replaced in the copy with Engine.GameInstance; authored maps, GameMode, input and /Game/Hyper remain. Linux SM6 and two shader workers match tested acceptance. Engine plugin defaults must stay enabled. Use the validated unified engine, not an engine with mismatched plugin metadata.

Online HOI/Steam/EOS requires explicit provider, GameInstance and networking acceptance and is deliberately refused here. Godot gameplay logic is not converted by GLB. A staged project is editable content, not proof that subsequent project modifications compile or play. Keep all project outputs/checkpoints beneath that project's directory.
