# WatooM Unified Blender Pipeline v3

Versioned helper source, upstream package, profiles, hash manifest, unattended fix and validation suite live under `/data/ai/helper-scripts/watoom-blender-unified/releases/v3.2-godot-path`. IaC contains deployment policy and locked profile copies only. No existing Blender 4.2/OpenCode job or model configuration is replaced.

Deploy on the homelab as root: `ansible-playbook -i localhost, ansible/playbooks/watoom-blender-unified-v3.yml -e unified_approved=true`. Package and manifest hashes are checked before transactional activation. No third-party download occurs. The installed archive hash and validation receipt are in `config/blender-unified-v3/release-lock.json`.

Run `python3 /data/ai/helper-scripts/watoom-blender-unified/current/runner.py --help`; modifying/executing modes require `--i-approve` and fresh isolated output paths. Read the release README for mode-specific flags and limits. Blender 5.2.1 and Godot executables are hash-pinned. Jobs use bounded CPU/memory without GPU access.

Validation: `python3 /data/ai/helper-scripts/watoom-blender-unified/current/validate_suite.py --i-approve`. This tests real headless geometry, UV/LOD, Rigify deformation, animation/NLA/root motion, constrained ragdoll baking, rendering, export/reimport, Godot animation/physics and isolated automatic/explicit rollback. Fixtures are synthetic, not finished human assets. Native Unreal skeletal/animation/PhysicsAsset creation is validated separately; body inspection and native physics simulation are unqualified.

MPFB, Sims 4 Studio, s4animtools, TS4 Creator Tools and AI Render remain blocked until source/licence/revision/compatibility verification and isolated runtime tests. Sims preflight never declares assets game-deployable. Existing SDXL is discovered, not invoked; no active inference job is interrupted. The legacy LLaMA-Mesh CPU adapter uses a request-only toolkit override; the old configuration and generation admission remain unchanged.

Rollback: use the activation snapshot printed by deployment: `python3 /data/ai/helper-scripts/watoom-blender-unified/releases/v3.2-godot-path/fix.py rollback --snapshot SNAPSHOT_JSON --i-approve`. It restores the previous owned current pointer, retains all releases and assets, and refuses a changed pointer. Failed activation rolls back automatically. The protected tar archive preserves release code; its SHA256 is locked in IaC. Before restoring a damaged release, verify that archive digest; do not overwrite assets or bypass integrity checks.

## Release integrity and runtime receipt

The current locked release is **v3.2-godot-path**. The lock's validation pointer targets `.../runtime/validation.json`, carrying the `godot` and `blender.checks` gates used during `fix.py install`. The previous top-level `validation.json` lacked these fields and tripped `BLOCKED 'godot'`.

Read-only release integrity check:

```bash
python3 /data/ai/helper-scripts/watoom-blender-unified/releases/v3.2-godot-path/fix.py check
```

The owner-approved activation playbook runs that check, then `fix.py install --validation <release-lock.validation> --i-approve` using the exact receipt in `config/blender-unified-v3/release-lock.json`. Use `fix.py rollback --snapshot SNAPSHOT_JSON --i-approve` with the activation snapshot to undo it. Neither install nor rollback is authorised by documentation updates; activation still requires the owner-gated playbook above.

## Verified Godot particle adapter
Version v3.1-particle-alpha adds `runner.py particle-vfx --request REQUEST.json --i-approve`. The locked registry is `config/blender-unified-v3/particle-recipe.json`; read the recipe README for the explicit RGB-mask/RGBA/opaque policy and fresh output schema. The runner verifies registered hashes before applying defaults and mandatory rendered alpha/draw-pass checks. The separate recipe Git commit is `9f4a3d7ac78763727bec75bc46ca483c71ce05b4`. Existing Blender modes are unchanged. Re-run the existing approved activation playbook; its previous pointer snapshot provides rollback.
