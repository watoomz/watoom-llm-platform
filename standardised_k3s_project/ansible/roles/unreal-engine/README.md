# Unreal source build

This role is the normal clean-checkout build path. It needs the existing build user, Linux build prerequisites, and that user's licensed Epic GitHub access. It does not depend on recovery reports, overlays, old binaries, helper scripts, private keys in Git, or purchased content.

From standardised_k3s_project:

    ANSIBLE_CONFIG=ansible/ansible.cfg ANSIBLE_ROLES_PATH="$PWD/ansible/roles" ansible-playbook -i ansible/inventories/homelab/hosts.yml ansible/playbooks/unreal-engine.yml -e unreal_engine_build=true

Limit the inventory to the intended build host when it contains multiple machines. A failed memory/storage preflight requires freeing capacity safely; this role never scales a running application, model or game.

The pinned engine source is UE5.8.3 commit396c9f059903aed5fec78ecd3d437a40c6415368. Official Setup/GenerateProjectFiles and complete ShaderCompileWorker/UnrealEditor targets generate their own matching module metadata. Do not use module-only output as a complete runtime build, disable required engine defaults, or manually patch BuildIds.

Outputs use /data/ai/toolchains/unreal/5.8.3; seven actions,12GiB/8CPU and a24-hour per-target bound are explicit defaults. A rerun uses ordinary UBT incremental behavior. No recovery supervisor is part of the resulting engine.

Breakpad generation is omitted by NoDumpSyms; matching debug-sidecar symbol acceptance is separate. This role does not certify symbols, gameplay, rendered fidelity, online providers, or deploy an engine just because compilation succeeded.

Validation so far: Ansible syntax PASS. Actual fresh-checkout build NOT TESTED; current isolated acceptance build is separate evidence. Before promotion prove version/libraries,C++ fixture,commandlets,required plugins,rendered play,restart and Unreal→GLB→Godot regression. Keep the previous accepted engine until the new output passes.

Hyper projects retain normal engine plugin defaults. GameInstance is selected per project/network profile; offline fixtures do not establish HOI/Steam/EOS integration. Never overwrite a user's Config directory wholesale.

An existing licensed Git mirror may be selected with -e unreal_engine_repository=/path/to/mirror. The pinned commit is cloned into a separate clean checkout; dirty working files, binaries, caches and recovery overlays are not inputs. The process-scoped safe.directory exception trusts only that explicitly selected source. No shared-object alternates/reference checkout is used.

## Runtime publication

The normal build can also publish a self-contained versioned runtime with explicit unreal_engine_publish=true and unreal_engine_publish_sha256 set to its validated editor hash. Publication preserves engine source/generated headers/build products for C++ project work but excludes Git metadata, saved files, DDC and historical recovery markers. It refuses existing releases, external/absolute symlinks, hash changes or insufficient storage. It never promotes a deployment automatically.

For an already built output, ansible/playbooks/unreal-engine-publish.yml invokes the same publication tasks without rebuilding. The source defaults to the normal clean-build output. Explicitly selecting an existing accepted output is artifact publication, NOT evidence that a fresh source build ran. Validate the relocated engine and regression before updating a runtime mount or pin. Partial failed releases are preserved for inspection; they are never silently overwritten.

## Matching debug crash symbols

The maintained tools/unreal/backfill-crash-symbols.py accepts --engine-root for a published runtime and optional --baseline-root for the previous accepted engine. A baseline selects only changed ELF build IDs; unchanged modules retain their prior coverage. Use --evidence with a fresh private reports directory and --budget-hours4 for a bounded targeted pass. Modules without matching debug sidecars are outside this coverage.

Each serial isolated CPU worker has6GiB/2CPU/300s bounds and requires8GiB measured host headroom. No engine rebuild is performed. check-crash-symbols.py uses the normal worker specification, not historical report templates. Generation requires matching debug build IDs and genuine FILE/FUNC records. Existing real symbols are preserved unless their exact bytes or decoded address/line/file/function mappings match the preserved baseline (source-root prefixes normalized) and the module build ID changed; that proven stale file is privately backed up before atomic replacement. The executable hash and original installation remain unchanged.

Capacity lending is separate from symbol generation. Existing guarded model/game capacity controls may watch symbol-coverage.json; active native work and real inference slots must be idle before model lending. Exact prior replicas are restored after completion/failure. Never direct-scale around the GPU owner.

Real symbols that match the freshly generated mapping are preserved and certified without replacement. A different existing mapping is replaced only when it is proven to be the older baseline mapping and the ELF build ID changed. Four-byte record counts, packed records and newline-delimited strings are read from the maintained UE encoder format; line/address/function differences are never normalized away.
