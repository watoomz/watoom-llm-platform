# Blender production status


## Production

Production is **watoom-code/watoom-code**, reached at [watoom-code](https://watoom-code.internal.homelab.example). The existing coordinator/builder/investigator/reviewer hierarchy, specialist registry, AgentMemory and authentication remain. No new MCP server, inference engine or Blender addon was deployed.



## Production images and execution paths

- Application is now 127.0.0.1:5000/watoom-code@sha256:b35f66f43638a6d66441b9ed752c18473fc0a2b37279b12cfc3b6d65a06d1cc1 after the separately validated Prompt Builder UI release. The Blender worker remains unchanged.
- Toolkit/controller/worker is now 127.0.0.1:5000/watoom-toolkit@sha256:3e8ac07deb09b4e3011c818386027bab7a604991c86f18b588a1f89bd5f3f748, from committed source fe37aa5ea85d9489c7fa39f80a3722a941919cbe.
- AgentMemory remains sha256:979134cb586355234e1acb6fd426e7bd1bd96734a647a59b207c8d24e45f0f3a.
- Worker Blender is 4.2.23 LTS; Godot is 4.7.2. The host Blender 5.2 is not substituted into this pipeline.
- Unreal 5.8.3 is pinned at /data/ai/toolchains/unreal/5.8.3/runtime-74dc43e1a653; editor SHA-256 is 74dc43e1a653fe3a46f68a1b3db6c3500d04d0f68a8878c9aa1b76b36a08fad3. Workers mount it read-only at /unreal-engine. /data/ai/assets/unreal-engine and wrapper paths are not executable discovery proof.

The Blender cutover changed only Toolkit/worker image pins, Toolkit source provenance in IaC and three existing native descriptor fields: modelSha256, configurationSha256 and sourceCommit. Application, AgentMemory and inference Deployment specs were preserved. The global asset catalogue and existing agents were not replaced. Existing native/Toolkit fences, snapshots, service drain, runtime identity checks and automatic rollback were reused.

## Native skills and supported scope

**All 22 pinned EL4CTEO skills plus watoom-blender-asset-builder are installed natively.** The Blender cutover registered 84 skills including the 61 pre-existing entries. The subsequent Prompt Builder release added a creator and 27 pipeline prompting skills, bringing the current total to 112; these are not all Blender execution skills. Relevant skills load on demand, keeping entire libraries out of the coordinator context.

EL4CTEO commit 71d031dab8bc6729504d11a78cbe91945401045f is MIT-licensed. Authoritative ported scripts, per-file provenance, original skill bodies and licence are maintained in ansible/roles/watoom-code/files/skills. The reproducible 4.2 port and request runner live in tools/blender-asset-builder. Selected anatomy/silhouette and bounded-scene guidance from pinned arjun988 and nicceasy sources is documented separately. Kevinbadi source remains assessment-only; no unlicensed code or text was redistributed and camera concepts were implemented independently.

Real Blender 4.2 validation covered 20 isolated upstream test modules: **46 passed, zero failed, four explicitly skipped**. Separate Cycles CPU studio/turntable renders passed. Supported tests exercise modelling, sculpting, retopology, UVs, baking, PBR, Rigify binding/checks, animation baking/root motion, export roundtrips, Geometry Nodes, classic cloth/rigid bodies, weather and scene tools. Native skill loading and real production agent execution were also exercised.

Limits remain explicit: GPU-context EEVEE/Workbench previews were not tested; direct GPU selection in the production rendering/baking scripts is rejected. Built-in Geometry Nodes cloth requiring Blender 5.2 is unsupported; classic cloth passed. Nishita sky uses an approximate inherited irradiance table, not calibrated 4.2 photometry. White-point temperature compositor grading is unsupported; saturation/fog glow are available. Optional unavailable meshopt/image-encoding preset options warn about fallback. No optional cloud/image-to-3D runtime was installed.

A native-skill reconciliation exposed and fixed an existing private-instruction copy bug: recursively copying with file mode 0644 removed root-directory traversal. The role now creates the private instruction directory explicitly and copies its existing SKILL.md as a file. Two repeat applies changed nothing; the original private instruction bytes and all 61 previous skill bodies remain available. Private content stays on the server.

## Request workflow, evidence and recovery

Use a new version under /data/ai/projects/llm/pipelines/blender-asset-builder. The production coordinator authors a reference/provenance record, specification and appropriate Blender scripts for the request. Generation uses agent-authored Blender code and selected installed skills; the reusable runner is not limited to the old magpie/prop/environment adapter.

The supported command inside the production builder session is python3 /config/skills/watoom-blender-asset-builder/scripts/pipeline.py --request <revision>/request.json. Its --dry-run shows the plan. Required unique stages include MODEL, MATERIALS, QA and EXPORT. Source/input/script/output hashes, real exit results, logs and attempts are durable. Start model scripts with an empty scene and QA all intended runtime geometry. The `--root` pilot mode is for diagnosis only, not the production entry point.

After EXPORT, automatic SOURCE_QA reopens the actual packed engine source, checks every runtime mesh against the geometry QA object set and triangle count, and repeats strict topology/UV checks. The QA output must contain the real upstream object metrics; finalize runtime names before QA and save source/export before adding preview floors. A real negative control rejected a GroundPlane that engine import alone had accepted.

Resume with --resume. Changed validated inputs require a new revision. After investigating a failed/interrupted local stage, --retry-failed permits one retry and retains partial outputs. Actual SIGKILL and SIGTERM tests proved that the owned Blender child stops, previous model hashes stay unchanged and the corrected workflow resumes. This is not a mocked recovery check. Native uncertain jobs must be reconciled rather than blindly replayed.

For engine acceptance, the coordinator calls the directly exposed watoom_specialist_run with specialistID local-toolkit, capability 3d.inspect, a unique job, and payload task=3d-inspect, canonical pipelines source path, parameters.engine_validation=1 and timeout=420. It then resumes with --engine-job <native job>. The runner requires a completed matching native database receipt, exact source hash, published artifact hashes and actual Godot/Unreal PASS results. An authored JSON PASS flag or an unrelated previous job cannot satisfy this gate.

Artifact references map under the existing generated mount: artifact:generated/watoom-toolkit-3d/v1/<id>/manifest.json is /generated/generated/watoom-toolkit-3d/v1/<id>/manifest.json inside the app. Read that exact path; do not search the whole filesystem for receipts. Searches and commands remain bounded and task-scoped.

Visual/reference/deformation review is independent of geometry checks. The reviewer records actual observations and hashes of at least two inspected rendered images. Delivery closes only when local stages, native engine evidence and explicit image review pass. Failed drafts remain preserved. An initial owned smoke revision failed visual review because of stray startup geometry; its corrected revision clears the scene and checks for unintended meshes.

## Real production acceptance

The production native specialist passed independently generated creature, prop and environment fixtures. Checks include Blender export/reimport; Godot actual import and skeletal playback; Unreal static/skeletal import, skeleton hierarchy, animation sequences, materials/textures, scale, collision, repeatable reimport, saved dependencies, fresh-editor actual playback and two LODs. Unreal uses disposable projects; Wombat and Moonstone content was not overwritten. Technical receipts and actual render reviews remain separate records.

Magpie v22 has **43,890 triangles**, complete skin weights and Idle/Walk/Flight clips. Actual multi-angle standing, walking and flight renders were compared with the retained reference photos. The selected art direction is funny and stylized, occasionally dark: a recognizable pale wedge bill, white nape/wing patches, charcoal body, long tail, expressive head and exaggerated game shapes. The stylized game baseline passed scoped reference/deformation review; that assessment is not a claim of photoreal anatomy or the user's personal artistic approval. Original 229,350-triangle source, v17 and failed refinements remain intact.

The request runner completed a real production native builder task through modelling, PBR, QA, export, CPU previews, native engine verification and image review. AgentMemory saved the verified recipe, returned its complete fields in another session, and the parsed recalled JSON was actually reused for a production environment engine job. The existing memory service was retained.

A separate native builder authored a new bench request and task-local geometry/material/export scripts from the brief. With coordinator API/geometry feedback and independent QA, corrected v10 passed all local stages, mandatory final-source QA, real production Godot/Unreal validation and actual front/perspective image review. It contains 16 runtime meshes, 192 triangles, two PBR materials and UVs, at 1.6 m width and 0.85 m height. A preceding v9 passed import but was rejected because its packed source included preview GroundPlane geometry. That failure is preserved and prompted the mandatory final-source gate; its receipt cannot close v10. This demonstrates a bounded native-authored prop workflow with review, not guaranteed unattended artistic success for arbitrary briefs.

Workers are tokenless CPU jobs, two cores and 3 GiB for engine acceptance, with no GPU allocation. Engine admission requires at least 5 GiB host memory available and retains a 2 GiB reserve. Inference/GPU settings remain unchanged; the live GPU power limit remains 250 W. Local primary-model requests during native smoke testing use the existing inference service.

## Pod retention

Normal Toolkit Jobs retain finished resources for 60 seconds. Owned diagnostic/compatibility Jobs use 3600 seconds to retain failure evidence. Both successful and failed terminal Jobs expire through Job TTL; reports and assets persist independently under /data/ai. A completed pod visible within that hour is expected.

Older Evicted ReplicaSet pods are not governed by Job TTL. Kubernetes PodGC is threshold-based, not a per-pod timer. No generic pruner or cluster GC setting was changed. References: [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/#ttl-mechanism-for-finished-jobs), [Pod lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#garbage-collection-of-pods).

## How to prompt in production

Open [watoom-code](https://watoom-code.internal.homelab.example) and paste a task below into the existing coordinator. Glance is the guide; run these prompts in watoom-code. Specify the target engine, intended size, triangle budget, animation clips and references. Ask the coordinator to inspect installed capabilities and load only relevant skills before execution. The builder authors task-specific geometry and scripts; complex assets can require investigation and revision.

### Discover and plan safely

```text
Inspect the production Blender tools and native skills available in this session. Report which EL4CTEO skills are actually installed and which scripts are validated on Blender 4.2.23. Plan a bounded asset task using the existing specialist workflow. Identify unsupported steps before executing them. Preserve source assets and unrelated game changes; use CPU jobs under the existing admission limits.
```

### Funny, occasionally dark magpie

```text
Refine the existing magpie v22 into a funny stylized Australian magpie with occasional dark, mischievous expressions and ominous poses. Preserve readable anatomy and black/white plumage. Inspect existing reference photos, source and state before changing anything. Target Godot 4.7.2, under 50,000 triangles, with Idle, Walk and Flight. Save a new revision; preserve v22. Show actual front, side, flight and expression renders for review. Validate weights, source animation, exported GLB and real Godot playback. Report technical and visual results separately. Do not change gameplay or declare visual acceptance for me.
```

### Game prop

```text
Create a stylized weathered wooden supply crate for Godot 4.7.2, one metre wide, under 1,000 triangles, with simple collision and a reusable material. Inspect the installed Blender skills and execute only supported Blender 4.2 operations. Save source and GLB as a new asset revision. Validate scale, normals, triangle count, materials and actual Godot import. Return the output paths, real preview renders and any failed checks.
```

### Environment piece

```text
Create a small stylized park pavilion for Godot 4.7.2, approximately six metres wide, under 10,000 triangles, with walkable clearance and simple collision. Match the funny, slightly dark magpie game's art direction. Use the existing Blender specialist and relevant installed skills. Preserve source and export separately. Validate scale, collision, material dependencies and a real Godot scene import, and show actual renders before calling it visually finished.
```

### Use an owned Fab asset

```text
Find the German Shepherd 3D Dog Model in the existing global asset catalogue. Inspect its actual formats, licence/provenance and dependency inventory. Preserve the acquired server package. Plan the supported route into Godot 4.7.2; use Unreal only if the selected source requires it. Work on a separate revision. Validate scale, materials, skeleton, animation and real engine playback, reporting any unsupported conversion explicitly. Do not download or duplicate the whole library.
```

For another pack, substitute its exact name from the table below. MetaHuman source ownership and catalogue registration do not establish a supported portable character conversion.

### Request evidence and recovery

```text
For this asset task, return the source and export paths, tool versions, selected skill names, executed checks and durable evidence paths. Distinguish PASS, FAIL, unsupported and not run. If a step fails, preserve its logs and partial outputs, diagnose the cause and resume from the last validated stage without overwriting the original. Do not claim Unreal validation unless an actual supported worker performed it.
```

The extended engine inspection worker is now production functionality. The coordinator uses the existing native local-toolkit specialist with explicit engine_validation=1; the user can simply request real Godot and Unreal checks. Keep the supported CPU/4.2 limits above in view; installation does not certify every upstream 5.2 feature.

## Fab assets on the server

All five requested packs are verified source acquisitions under /data/ai/assets/fab and discoverable through the existing single global catalogue and read-only library mounts:

| Pack | Directory | Catalogue records |
|---|---|---:|
| German Shepherd 3D Dog Model | german-shepherd-3d-dog-model-069c4300 | 27 |
| Ultimate Metahuman Body: Base Adult (Male & Female) | ultimate-metahuman-body-base-adult-352654c4 | 6 |
| Free Medieval Assassin Girl | free-medieval-assassin-girl-cd01c311 | 162 |
| Free Casual Girl Sample (Modular) | free-casual-girl-sample-modular-336eca27 | 412 |
| Rogue Character Model | rogue-character-model-dd1f46ae | 311 |

The four Unreal packs were downloaded by the existing authenticated server downloader with length/SHA-1 verification. MetaHuman was downloaded temporarily through the owned desktop Fab page, then transferred to the server with user authorization. The server mhc_base.mhpkg is 481,892,864 bytes; SHA-256 e68ef3c21c829e4213aaf6a7df1fb9fb2b981ef12a801a6be8751a6e1c92caa0. Both male and female sources are present. The original package remains, alongside a separately extracted source-package inventory. Six source assets were registered and hash-verified through the installed bounded Catalogue index_selected method.

Acquisition/catalogue discovery is not Unreal/MetaHuman import or Godot conversion acceptance. Preserve source packages and /Game dependency namespaces. There is no per-project copy of the entire library. A supplementary full-library refresh reached its 100-batch safety bound and retained its cursor; the five requested packs are independently verified and registered, and existing records/adapters remain intact.

## Evidence and rollback

Current evidence root: /data/ai/helper-scripts/watoom-blender-package/production-skills-20261020T093543Z.

- Native activation and exact owned recovery upgrade: live-native-release, live-native-recovery-upgrade and live-native-source-qa-upgrade.
- Toolkit cutover, private config/database snapshots, previous immutable manifest and protected Deployment specs: live-toolkit-release.
- Three native production engine receipts and full request state: production-engine-smoke.
- Cross-session production memory and actual recipe reuse: production-memory.
- Actual forced-interruption recovery: /data/ai/projects/llm/pipelines/blender-asset-builder/acceptance-interruption-v2-20261020/result.json; includes zero-exit missing-output rejection.
- Real final-source positive/negative controls: /data/ai/projects/llm/pipelines/blender-asset-builder/acceptance-final-source-gate-20261020/result.json.
- Native-authored bench full acceptance: production-engine-smoke/autonomous-bench-v10-validation.json.
- Final authenticated published UI and deployment/idle audit: final-gui and final-runtime-audit.
- Latest magpie source, renders, QA and durable state: /data/ai/projects/llm/pipelines/blender-asset-builder/magpie-v22-20261020.
- Original engine and isolated rollback/durability evidence: /data/ai/projects/blender-asset-builder/production-20261020T074548Z/reports.

The scoped rollback command is maintained in the existing deployment coordinator: --rollback-blender-evidence <live-toolkit-release> --iac-root <authoritative repository> --evidence <new private evidence directory> --i-approve. The helper prints its risk warning, requires idle native/worker admission, verifies exact current configuration and immutable previous image, and restores only Toolkit image/binding/IaC pins. It does not restore an older user database, delete assets or remove compatible native skills. Concurrent changes refuse rollback. An older Toolkit image disables the extended engine inspection path until re-promotion. Rollback failure retains admission ownership and recovery evidence.

The server operator helper /data/ai/helper-scripts/watoom-blender-package/scripts/run-watoom-blender.py shows the current production entry and supports --request <request.json> --dry-run. Actual execution stays inside the existing native builder session. Scoped production rollback can also be invoked with sudo python3 /data/ai/helper-scripts/watoom-blender-package/scripts/run-watoom-blender.py --rollback-production --i-approve.


The guided [Prompt Builder](https://watoom-code.internal.homelab.example/prompt-builder) now collects dimensions and requirements with editable safe defaults. See [Pipeline prompts](PIPELINE_PROMPTS.md).
