# MOSS Image: getting the GPU through the GPU ownership controller (design, not implemented)

## Why this is needed

The GPU (20 GiB) is held by the primary Qwen LLM (about 18.5 GiB in use). MOSS-Image in `min_memory` mode needs about
4 GiB of VRAM and 4 GiB of RAM, so it cannot run beside the LLM. Today the service's GPU gate refuses to start the engine
(`gpu_busy`). The controller is the sole GPU replica writer; bypassing it (scaling the LLM down by hand, `kubectl`, killing
processes) is forbidden by the repo rules.

## What the controller offers today (read from the source, not tested here)

`tools/llm/watoom-gpu-controller` serves a Unix-socket RPC (`client.GPUClient`) with these actions:
`status`, `begin(job)`, `activate(job, generation)`, `restore(job, generation)`, `can-use-qwen`. Recovery is deliberately not exposed.
The Mesh pipeline (`ansible/roles/llm-model-lab/files/llama_mesh_pipeline.py`) is the precedent:
`begin` returns a generation, `activate` stops Qwen and starts the Mesh deployment, `restore` brings Qwen back; one
request id maps to one job, receipts prevent a second job, and an uncertain outcome is never retried with a new id.
`Controller.switch_to_mesh` is hard-wired to scale the primary down and the **Mesh** deployment up and to require that
deployment to become healthy, so MOSS-Image cannot use `activate` as it stands.

## Options

| | Change | Size | Risk |
| --- | --- | --- | --- |
| **A. Host-specialist activation (recommended)** | Add a controller action that stops the primary LLM, verifies GPU memory is released, records `host-specialist-active` with the job and generation, and starts no Kubernetes deployment. `restore` reuses the existing restore path. MOSS runs as the existing host process. | Medium: one new phase, one action, tests | Touches production GPU scheduling; needs the full offline suite, review and the existing activation gates |
| B. MOSS as a second specialist deployment | Generalise the controller from "Mesh" to N specialists and ship MOSS as a Kubernetes deployment | Large | Largest blast radius |
| C. Operator hand-off | A human stops and restores the LLM around image sessions | None | Error-prone and bypasses the controller; not acceptable as a standing design |

## Recommended behaviour (option A)

- **GPU sessions, not per-image swaps.** Reloading the LLM takes minutes, so the page gets an explicit "Start GPU session"
  (LLM paused, engine loads) and the session ends on a button or after an idle timeout (restore the LLM, stop the engine).
  The page shows Locked, Starting, Ready, Restoring, and the LLM-restore result.
- **Order on start:** `status` must show `qwen-ready`, no owner, not uncertain, and no in-flight inference lease
  (the controller already refuses otherwise). Then `begin`, then the new activate-host action, then start `moss-server`.
- **Order on end:** stop `moss-server` and confirm VRAM is freed, then `restore`, then verify the primary is healthy.
- **Failure rules copied from Mesh:** request ids are stable and never regenerated after an uncertain outcome; a crashed
  service must run the same recover-queue path before anything else; never write ownership state by hand.
- **Service changes:** replace `Manager._gate` with a `gpu_session` module built on `GPUClient`; keep the VRAM check as a
  second, read-only safety net. Jobs submitted with no session either queue until one starts or fail with `gpu_session_required`.
- **Authentication:** the controller socket is UID-restricted. The service must run under an allowed UID, and the page must
  sit behind the existing authenticated proxy, because "pause the LLM" is a privileged action.

## Not decided (needs the owner)

1. Option A or B.
2. Idle timeout before the LLM is restored (suggested 10 minutes) and a hard maximum session length.
3. Whether an active WatooM Code session may be interrupted, or the start must wait for native admission to be idle
   (the model-manager's native admission check exists for this and is the safer default).
4. Which UID runs the service.

## Acceptance before any live use

Controller offline tests (the existing 102, plus new ones for the host-specialist phase, fencing and rollback), a
rehearsal on the stage namespace, a recorded restore of Qwen, and an explicit go-ahead for the production Ansible apply.
Also pending separately: a smoke test of the downloaded `moss-server` binary, and a first real generation.
