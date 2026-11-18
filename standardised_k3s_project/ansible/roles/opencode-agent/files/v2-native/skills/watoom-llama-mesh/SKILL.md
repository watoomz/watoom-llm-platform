---
name: watoom-llama-mesh
description: Generate and retrieve 3D game assets through WatooM's durable LLaMA-Mesh pipeline; use for geometry requests, OBJ/GLB generation and Magpie candidates.
---

# WatooM LLaMA-Mesh

Use the configured `watoom-llama-mesh` MCP server. Its tools are `submit`,
`status`, `list`, `manifest`, and `retrieve` (OpenCode may prefix server names).
The host pipeline owns GPU switching, queue locking, Blender cleanup and Qwen
restoration. Submission is asynchronous; Qwen is unavailable temporarily while
the specialist model uses the GPU. Preserve the returned job ID across turns.

1. Determine the requested asset and geometry constraints. Write a concise
   geometry prompt requesting a complete Wavefront OBJ with triangular faces.
2. Call `submit` with `prompt`, a safe `name`, and supported optional `seed`,
   `temperature`, `max_tokens` (1–7000). Do not submit duplicate retries.
3. Record `job_id`; call `status` periodically. Pending means queued; running
   includes the actual phase. On failure, read manifest and diagnose the stage.
4. After state `complete`, read `manifest`. Check `result`, raw and cleaned
   validation, GLB validation, warnings and primary restoration evidence.
5. Call `retrieve`. It copies verified OBJ/GLB and manifest into
   `/workspace/.watoom/llama-mesh/JOB_ID/`, and existing PNGs when present.
6. Inspect the actual geometry with installed Blender tools. The pipeline does
   not create renders by default: use Blender to render side, front,
   three-quarter and top views in the retrieved workspace directory.
7. Prepare materials and game workflows with existing Blender/Godot tools.
   No rig, accurate coloration or animation readiness is implied by generation.
8. Report actual paths, validation classification and observed visual defects.
   REPAIRABLE raw topology is a prototype requiring review, not a clean PASS.

Example submission arguments:

```json
{"prompt":"Create a simple low-poly rounded rock. Return one complete Wavefront OBJ mesh with valid vertices and triangular faces.","name":"rock-smoke","max_tokens":7000,"seed":42}
```

Use the returned ID as `{"job_id":"ACTUAL_RETURNED_ID"}` for status,
manifest and retrieve. For operator diagnostics the identical client is:

```text
python3 /home/opencode/.config/opencode/watoom-tools/watoom-llama-mesh.py list
```

Never search arbitrary workspace trees to find the homelab, attempt SSH by
default, assume host paths are mounted, scale model deployments, modify inference
settings or bypass queue locking. Never claim completion without durable complete
status and existing outputs, or claim game readiness without passed validation
and geometry review. Never invent assets, renders, materials or rigs.
