# Host Tuning and Capacity

Current deployment snapshot: 13 October 2026. Runtime-specific status is dated; configured/recovery guidance is not an end-to-end test.

## Current host shape

- Fedora 44 Server
- AMD Ryzen 5 5500, 6 cores / 12 threads
- 32 GiB RAM
- NVIDIA GeForce GPU 20 GB
- k3s `v1.36.3+k3s1`
- Docker via Fedora moby-engine

Current GPU observation at documentation collection: driver `615.71.09`, CUDA 13.4; power limit 250 W (13 October 2026); persisted startup policy agrees.

## Live tuning (checked 13 October 2026)

- tuned profile: `throughput-performance`
- TCP congestion control: BBR
- qdisc: fq
- `vm.swappiness=10`
- `vm.dirty_ratio=15`
- `vm.dirty_background_ratio=5`
- `fs.inotify.max_user_watches=1048576`
- `fs.file-max=2097152`
- journald configured target cap: `SystemMaxUse=512M` (not requalified live in this pass)

## Capacity risk

Historical audit evidence identified `/` as the main pressure point, with `/var/lib/rancher/k3s`/containerd images and snapshots the largest root consumer. Do not automatically prune k3s/containerd during rebuild. Confirm health and disk pressure first, then perform explicit image/snapshot maintenance.

```bash
df -h / /app /data
sudo du -xhd1 /var/lib/rancher/k3s | sort -h
```

GPU model/context tuning should be validated against the 20 GB VRAM ceiling and current desktop GPU usage. The router's one-large-backend-at-a-time design is part of that capacity control.

## Current capacity snapshot

13 October 2026: root 84%, `/app` 70%, `/data` 62% used. RAM exposed by the OS is about 30 GiB of the nominal 32 GiB hardware; approximately 14 GiB was available and swap use was 5.3 GiB at collection. These are transient observations, not resource limits. CPU, sysctl values above and the tuned profile were read live; no host tuning was changed.
