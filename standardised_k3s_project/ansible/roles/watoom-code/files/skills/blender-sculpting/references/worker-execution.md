# Shared Blender worker policy

Read scripts/worker-profiles.json for pinned binaries, hashes, devices and bounds. AUTO selects CPU on the server and OPTIX on the RIG; explicit CPU is allowed on the RIG. An unavailable requested GPU is an error, never a silent CPU fallback. Launch scripts headlessly in Blender; never import bpy scripts into application Python. Profile verification is an execution boundary check, not a worker dispatch API. The request pipeline remains a local runner and requires an already verified external worker; native capture supports only its declared capture/preparation modes.

Qualify GPU-context tests with BAS_SKIP_GPU unset on the RIG. Test review shots, lookdev turntables, Cycles and EEVEE; record actual results. Pixel review remains required for visual acceptance.

Version-dependent fallbacks remain conditional: Geometry Nodes cloth requires Blender >=5.2; 4.2 is unsupported for that feature. Meshopt/WebP export uses actual operator capabilities and reports unavailable options. Nishita approximation and unsupported white-point grading apply only to older runtimes, not a blanket 5.2 restriction. Do not claim feature support from a version number alone.

Capture job deadlines are distinct from the 300-second component-stage ceiling. Hash changes invalidate validated checkpoints. Keep failed outputs; no automatic replay after an uncertain execution.
