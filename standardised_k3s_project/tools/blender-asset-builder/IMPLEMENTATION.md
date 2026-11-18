# WatooM Blender Asset Builder implementation

Authoritative status, prompts, immutable versions, evidence and rollback: [Blender production status](../../docs/BLENDER_PRODUCTION_STATUS.md).

Production is watoom-code/watoom-code; the legacy canary remains suspended at zero. The existing native builder loads selected skills on demand and authors task-specific Blender scripts. pipeline.py --request delegates to request_pipeline.py, preserving the historical pilot separately. It checkpoints hashes and serial stages, retains failed outputs and supports bounded resume. Automatic SOURCE_QA reopens the final packed source and rejects runtime meshes absent from the upstream geometry QA. Real native database receipts and independent image review are required to close delivery.

The existing Toolkit 3d.inspect worker is promoted with real Blender 4.2.23, Godot 4.7.2 and pinned Unreal 5.8.3 validation, including fresh-editor playback and LODs. Twenty-two ported EL4CTEO skills and the production builder are native; 61 earlier skills remain. Forty-six upstream checks passed, four explicitly skipped; CPU render and actual interruption/recovery controls passed. Consult the status document for unsupported 5.2/GPU features.

IaC is maintained through the existing watoom-code role and release coordinator. Native skill updates and Toolkit image-only cutover use existing idle fences, snapshots and scoped rollback. No inference, networking or application image replacement is required. Source assets, rejected revisions, five acquired Fab packages and private evidence remain server-side.
