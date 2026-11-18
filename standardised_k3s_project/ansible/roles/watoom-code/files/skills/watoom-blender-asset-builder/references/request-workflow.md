# Request workflow contract

## Execution boundary (verified deployment)

The request runner is a local subprocess runner, not a worker dispatcher. `pipeline.py` / `request_pipeline.py` launch Blender in the caller's cgroup. Python wrappers, `start_new_session`, selecting a builder agent, `--resume`, `--retry-failed` and `--engine-job` do not allocate memory or move execution to the capture worker. The application cgroup is 2GiB; external workers are separately bounded: server CPU 4GiB or RIG Windows Job Object 8GiB. Profile verification does not turn this local runner into a dispatcher.

In the application shell, prepare metadata and use `--dry-run` only. Any non-dry-run invocation may start unfinished Blender stages. Execute those only through an explicitly verified external worker integration; this document does not provide such a launcher for custom stages. Never guess dispatcher options, nest subprocesses to evade the guard, or strip source assets to fit the app limit.

Exit `-9` means SIGKILL. Attribute it to OOM only with matching kernel/cgroup memory-event evidence; bone count and a missing report do not prove OOM. Preserve the failed attempt and report the missing route instead of retrying unchanged.


Use a fresh version directory under /data/ai/projects/llm/pipelines/blender-asset-builder. The existing coordinator authors geometry appropriate to the request; this runner executes task-local or installed skill scripts serially. It does not invent a mesh from the brief itself.

Required request fields: schema=1, brief, references (local provenance JSON), specification (local spec JSON), engine_source (local packed .blend), stages, optional visual_review. Stage names are unique and include MODEL, MATERIALS, QA and EXPORT. Each stage has script, optional blend and inputs, string args, output files and timeout (1..300 seconds). Script paths are task-relative or /config/skills; all inputs/outputs remain task-relative. Scripts must save each declared output explicitly. Include imported task-local modules (for example scripts/bench_geom.py) in stage inputs; a changed helper is a changed build input. CLI upstream scripts emit @@JSON@@ with ok/pass; either false fails the stage even with exit zero.

```json
{
  "schema": 1,
  "brief": "A weathered one metre wooden crate for Godot and Unreal",
  "references": "references/sources.json",
  "specification": "specification.json",
  "engine_source": "source/export.blend",
  "stages": [
    {"name":"MODEL","script":"scripts/model.py","outputs":["source/model.blend"],"timeout":180},
    {"name":"MATERIALS","script":"scripts/materials.py","blend":"source/model.blend","inputs":["source/model.blend"],"outputs":["source/materials.blend"],"timeout":180},
    {"name":"QA","script":"scripts/qa.py","blend":"source/materials.blend","inputs":["source/materials.blend"],"outputs":["reports/qa.json"],"timeout":180},
    {"name":"EXPORT","script":"scripts/export.py","blend":"source/materials.blend","inputs":["source/materials.blend","reports/qa.json"],"outputs":["source/export.blend","game-ready/asset.glb","game-ready/asset.fbx","renders/front.png","renders/side.png"],"timeout":300}
  ]
}
```

Use EL4CTEO qa_check.run and inspect its pass field in qa.py; write the actual result and raise on failure. Use the installed material/export/UV/rigging scripts where applicable. Include actual reference/spec hashes in stage inputs. For animated assets add explicit rigging/animation and deformation checks and preview images; static assets record animation not applicable.

After native 3d.inspect engine validation completes, resume with --engine-job <unique native job>. Native job body must reference this exact canonical engine_source, engine_validation=1, and the source hash must match its published manifest. A previous unrelated job or authored JSON cannot satisfy this gate.

The image reviewer writes reports/visual-review.json only after inspecting real images:

```json
{"status":"PASS","reviewer":"actual reviewer name","notes":"Concrete silhouette, reference, material and deformation observations; remaining limits","images":{"renders/front.png":"actual SHA-256","renders/side.png":"actual SHA-256"}}
```

A failed image review uses status FAIL and concrete repair notes. This is an assessment record, not a substitute for viewing the images. Do not change it merely to close a task.

Recovery: --resume revalidates completed output hashes, input hashes and script hashes. Changed validated stages require a new revision. Failed/interrupted local stages require log review; --retry-failed permits one retry and moves declared partial outputs to reports/retained-<stage>-<attempt>. Native uncertain jobs must be reconciled through the existing native specialist workflow; never blindly resubmit them. Original references, output revisions and failed logs remain.

The runner automatically adds mandatory SOURCE_QA after EXPORT. QA must write the actual qa_check result (or its upstream field), including validated object metrics. Finalize runtime mesh names before QA. SOURCE_QA reopens the packed engine_source and checks every mesh against that validated name set, triangle count and strict geometry/UV checks. Save packed runtime source and exports before adding preview floors or other render geometry. Extra preview meshes fail delivery even when engine import succeeds. SOURCE_QA is reserved and cannot be supplied by the request.
