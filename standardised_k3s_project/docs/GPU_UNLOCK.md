# Pinned GPU unlock on the Fedora host

Upstream: https://github.com/Zagitta/gpu-unlock
Reviewed revision: af28cbbfd3d922a659227ecfb7369adfd924cf03 (1.0.0).

Qualified host identity: Fedora 44, kernel 7.2.7-200.fc44.x86_64,
NVIDIA 615.71.09, PCI 0000:10:00.0 / 10de:2206, GPU 20GB,
Secure Boot disabled. This is not a claim that the unlock is active or faster.
The bundled firmware input version 610.43.03 does not replace the host driver.

## Reconcile

From ansible/: `sudo ansible-playbook -i inventories/homelab playbooks/gpu-unlock.yml`.
The dedicated playbook reuses gpu_host without running its power-policy tasks.
Defaults pin upstream and the local RPM release. Review both before upgrading.
Builds run as codex, using upstream SHA-256 verification and all five tests.
Generated local RPMs are unsigned; GPG checking is disabled only for that local
package transaction. Source and generated packages stay under /app/gpu-unlock.

A root-only recovery directory holds the first full /boot backup before install:
/data/ai/helper-scripts/reports/gpu-unlock-af28cbbf/boot-before.tar.
Do not replace that snapshot on repeat runs. It may contain sensitive boot data.
DKMS package scripts build all kernels with headers and regenerate initramfs.
The task checks the current kernel module and initramfs firmware before setting
`gpu_unlock.targets=0000:10:00.0` only on the running kernel entry. Older entries
remain unopted-in. No runtime driver unload, GPU reset, reboot, service restart,
network change, inference job or benchmark is part of this playbook.

## Activation and acceptance

An approved maintenance reboot is required. First checkpoint active application
jobs, arrange console/power recovery, and retain the older boot entries.
After reboot inspect `cat /proc/cmdline`, `journalctl -k -b` for gpu_unlock,
`lspci -Dnnk -s 0000:10:00.0`, and `nvidia-smi`.
Require an explicit unlock-success log, the original NVIDIA driver binding,
normal GPU memory/health and healthy application workloads. Loading a module on
an already-bound GPU does not establish success. Do not unload NVIDIA to test.
Measure a controlled identical BF16 workload before claiming a speedup; upstream
reports are hardware/workload dependent and do not predict decoding gains.
Future kernel entries must be reviewed for target opt-in; this playbook scopes
the argument to the currently running kernel rather than all boot entries.

## Rollback

Disable the scoped boot argument through the same playbook with
`-e gpu_host_unlock_boot_enabled=false` before rebooting. If the kernel version
has changed, remove gpu_unlock.targets from the affected boot entry explicitly
with grubby, or delete that argument in the bootloader edit screen. Alternatively
boot an older entry that has no target argument. The installed module is inert
without this opt-in. Do not restore the entire boot archive over a running system.
For complete uninstall, first disable the opt-in, remove gpu-unlock-dkms and
gpu-unlock-firmware with dnf, then check regenerated images and reboot during an
approved maintenance window. Review package-removal scripts before doing so.
If logs say firmware did not stop and DMA buffers were retained, upstream requires
a full power off before retrying. No automatic retries or reboot loops.

## Evidence

/app/gpu-unlock/build.log and install.log record build and Ansible execution.
The acceptance report and subsequent idempotence log are under the recovery
report directory. Preserve these alongside the immutable source revision.

## Activation verified, 25 October 2026 (Australia/Brisbane)

The authorized graceful reboot booted the same 7.2.7 kernel with the scoped target.
Kernel log: `pci 0000:10:00.0: gpu_unlock: unlocked`.
NVIDIA 615.71.09 still binds the GPU, reports 20480 MiB and the 250W cap.
The k3s node is Ready. Paired image probes passed on the projector-enabled
Qwen uncensored MTP route after reboot. No throughput improvement is claimed.
Full preflight, database snapshot, boot IDs, boot logs and recovery evidence:
/data/ai/helper-scripts/reports/gpu-unlock-af28cbbf/reboot-20261025.
