# llamAmpere production build (swift-qwen38-coder)

Production image: `127.0.0.1:5000/watoom-llamampere@sha256:3bb755f835b65f8d5e9db3ec0cd65ce860efd6633f4e0b7d6338c9b6286a8b2e`
(tag `sm86-943cbe35777c-async-candidate`, label `v0.6.2-watoom-async-disk.1`), adopted 2026-11-04.

Source: upstream https://github.com/JakeATX/llamAmpere at `e9193f81423a613e19336834c0bb76dd94dd3191` (v0.6.2)
plus `0001-async-disk-spill.patch`. Applied with `git am` and committer `Agent Export <codex@agent.example>`,
committer date `1793739307 +1000`, it reproduces commit `943cbe35777c98ed6696f3c411acb3bd40a8e67e`.

The patch writes prompt-cache disk spills on a background thread (`--cache-disk-async N`,
`LLAMA_ARG_CACHE_DISK_ASYNC`, default 1; 0 = synchronous). Before it, each ~2 GiB RAM eviction blocked the
server loop for 17-65 s on the /data HDD, so requests and /metrics scrapes stalled. Tests:
`test-prompt-cache-disk` 423/423, clean under ThreadSanitizer.

Build (heavy compile off the homelab server):
1. On Bazzite: `build-stage.Containerfile` with `podman build --target build --memory 10g`,
   `BUILD_JOBS=2`, inside a bounded user unit and a sleep inhibitor; copy `/stage` out as `stage.tgz`.
2. On the homelab: verify `stage.tgz` SHA256, extract, `docker build -f assemble.Containerfile` (copies only).

Evidence: `/data/ai/helper-scripts/reports/inference-perf-20261104-async-disk-build-01` (build) and
`/data/ai/helper-scripts/reports/inference-perf-20261104-cache-ssd-async-01` (fenced adoption, rollback manifest).
