# Host Tuning and Capacity

## Current host shape

- Fedora 44 Server
- AMD Ryzen 5 5500, 6 cores / 12 threads
- 32 GiB RAM
- NVIDIA GeForce GPU 20 GB
- k3s `v1.36.3+k3s1`
- Docker via Fedora moby-engine

GPU: driver `615.71.09`, CUDA 13.4, power limit 300 W.

## Tuning (`homelab_rebuild/tasks/tuning.yml`)

- tuned profile: `throughput-performance`
- TCP congestion control: BBR
- qdisc: fq
- `vm.swappiness=100` (swap is 8 GiB zram, so swapping is cheap compression, not disk I/O)
- `vm.dirty_bytes=1073741824`, `vm.dirty_background_bytes=268435456` (byte limits; `vm.dirty_ratio` is left unset so it cannot zero them)
- `fs.inotify.max_user_watches=1048576`
- `fs.file-max=2097152`
- journald cap: `SystemMaxUse` set by drop-ins in `/etc/systemd/journald.conf.d/`

## Capacity risk

`/` is the main pressure point, with `/var/lib/rancher/k3s`/containerd images and snapshots the largest root consumer. Do not automatically prune k3s/containerd during rebuild. Confirm health and disk pressure first, then perform explicit image/snapshot maintenance.

```bash
df -h / /app /data
sudo du -xhd1 /var/lib/rancher/k3s | sort -h
```

GPU model/context tuning should be validated against the 20 GB VRAM ceiling and current desktop GPU usage. The router's one-large-backend-at-a-time design is part of that capacity control.

RAM: about 30 GiB visible of 32 GiB installed. Check current use with `free -h` and `df -h / /app /data`; root and `/data` both run above 80%, so watch them before large downloads or image builds.
