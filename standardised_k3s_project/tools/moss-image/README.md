# MOSS Image Studio

A local web page and JSON API in front of the [mossimage.cpp](https://github.com/mossimage-cpp/mossimage.cpp)
`moss-server` sidecar (Apache-2.0), running the official MOSS-Image SFT model from quantised component files:
INT8 DiT (`high` tier), W4A8 text encoder and the FLUX.2 VAE (about 13 GB, from `Comfy-Org/MOSS-Image`).
The page has 52 camera / film-look presets that wrap your scene as `<look> <scene> <look>` with the recipe's own
negative prompt, as tested in <https://www.robertcreative.com/blog/moss-image-film-camera-prompts>.

**Status: live (2026-11-10).** Deployed by `ansible/roles/moss-image` (host service, bound to the k3s bridge 10.242.0.1:8791), published at `https://glance.internal.homelab.example/moss/` (route `manifests/10-infrastructure/glance/moss-image-route.yml`, pod-subnet firewall rule from the role). Latest images appear on the Glance Command Center. One real generation and a Qwen restore have been verified. The page has no auth of its own; it relies on the internal domain like the Model Manager.

## Layout

| Path | What |
| --- | --- |
| `moss_image_service.py` | stdlib-only service: HTTP API, one-job-at-a-time queue, sidecar driver, GPU gate, idle release |
| `web/index.html` | the page (scene box, preset picker, settings, progress, gallery) |
| `presets/film-camera-looks.json` | the 52 presets with source, author and a licence note |
| `gpu_session.py` | GPU controller session (quiet wait, begin/park-cpu/restore, idle timeout) |
| `deploy/` | example systemd unit, not installed |
| `tests/` | 22 offline tests using `fake_moss_server.py`, a protocol-2 stand-in; no GPU needed |

Run the tests: `python3 -I -m unittest discover -s tools/moss-image/tests`

## Where things are on the server

Engine, models and output live in `/data/ai/projects/images/moss-image` (override with `MOSS_IMAGE_ROOT`):
`engine/mossinfer-2.2.1-linux-cu13-x86_64/` (mossinfer v2.2.1 cu13 package, checksum-verified; the service finds `bin/moss-server` under `engine/`), `models/MOSS-Image-SFT/` (configs and tokenizer only),
`models/components/{dit,text_encoder,vae}/`, `src/` (clone of OpenMOSS/MOSS-Image, reference only) and `output/`.

## Running it by hand (needs free VRAM)

```
python3 tools/moss-image/moss_image_service.py --port 8791      # binds 127.0.0.1
```

`--mode min_memory` (default) needs about 4 GiB of VRAM and 4 GiB of RAM. The GPU gate (`--gpu-gate vram`, default)
refuses to start the engine unless `--min-free-vram-mib` (6144) is free, so this service never takes the GPU from the
LLM. `--gpu-gate none` disables the check and is for tests only. The engine is stopped, freeing the CUDA context,
after `--idle-release` seconds idle (300).

## GPU sessions

`--gpu-gate controller` makes the service take the GPU only through the WatooM GPU controller (`gpu_session.py`):
the page's "Start GPU session" checks that WatooM Code is not running anything (an unreadable check counts as busy; `--quiet-seconds` can require a longer quiet period, default 0), then
`begin` -> `park-cpu` (stops the primary LLM, starts nothing else) -> engine runs -> after 10 idle minutes (or the
button, or 2 hours) the engine stops, VRAM is checked, `restore` runs and the controller must return to `qwen-ready`.
Generation without a session is refused (`gpu_session_required`). A failed restore latches an error that the service
never retries; an operator reconciles the controller. The controller side registers `moss-image` as a host worker
(`HOST_WORKER_UNITS` in `tools/llm/watoom-gpu-controller/g3h_service.py`), so it only works as the main process of
`watoom-moss-image.service`. See `DESIGN-gpu-controller.md` and `deploy/watoom-moss-image.service.example`.

## Agent tools and crash recovery

- `plugin/` is a WatooM Code plugin with `moss_presets` (search the 52 looks), `moss_status` and `moss_generate`
  (one image, waits up to 10 minutes). It cannot start a GPU session: that pauses the LLM running the agent, so the
  operator presses *Start GPU session* in the Studio; without one `moss_generate` returns `no_gpu_session` and does nothing.
  Tests: `node --test tools/moss-image/tests/plugin.test.mjs`. Deploy (copy-only, needs a fresh WatooM Code session, off by
  default): `ansible-playbook ansible/playbooks/watoom-code-moss-image-plugin.yml`; remove with `-e watoom_code_moss_image_enabled=false`.
- `gpu_recover.py` runs as the unit's `ExecStopPost`. If the service died while it owned the GPU it asks the
  controller to `recover` (restore the LLM); the controller itself refuses unless the owner process is dead. A refusal is
  logged, never raised.

## Safety notes

- POSTs require `Content-Type: application/json` and refuse a cross-origin `Origin`; bodies are capped at 64 KiB.
- Output names are server-generated; only `^[0-9a-f]{32}\.png$` files in the output directory are served.
- Prompt text, size (max 2.1 MP, multiples of 16), steps (60) and CFG (10) are validated before the engine sees them.
- The preset text comes from the blog author's published recipes. Confirm reuse terms before redistributing.
