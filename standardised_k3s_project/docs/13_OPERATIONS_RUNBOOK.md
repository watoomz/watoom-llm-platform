# Operations Runbook

## Start-of-day / post-change

```bash
cd /data/github/watoom-standardised-homelab/standardised_k3s_project
git status --short
./ansible-run playbooks/health.yml
./ansible-run playbooks/validate.yml
kubectl get pods -A
docker compose ls
```

Review intentional `0/0` workloads before escalating.

## Restart one Kubernetes application

Use the registered application playbook when available:

```bash
./ansible-run playbooks/kubernetes-app.yml   -e kubernetes_app_name=<name>   -e kubernetes_app_action=restart
```

Do not delete pods as the first response when the desired-state owner already provides a bounded restart action.

## On-demand game server

Use the game playbook/menu entry for registered game servers rather than editing replicas in manifests. Confirm required Secrets before start.

## Docker stack

Use the registered Docker stack controls/menu. For incident diagnosis before restart:

```bash
docker compose ls
docker ps -a
docker logs --tail=200 <container>
```

## LLM model selection

Normal requests use the controller-compatible LLM router. The G3H controller is the sole GPU replica writer; the router has no direct scaling fallback. Mesh generation uses its OpenCode MCP pipeline with a stable request ID. Never manually scale GPU backends, reset ownership or bypass admission, including during debugging. Read live ownership/worker state before any recovery.

## Image drift

```bash
./ansible-run playbooks/image-audit.yml -e image_audit_action=export
./ansible-run playbooks/image-audit.yml -e image_audit_action=check
```

The live image lock is audit evidence, not permission to retain floating tags indefinitely.

## Before reboot

```bash
git status --short
kubectl get pods -A
docker compose ls
df -h / /app /data
```

If there is an active LLM job, note the selected backend and GPU state.

## After reboot

```bash
ip -br addr
ip route
systemctl --no-pager --failed
kubectl get nodes -o wide
kubectl get pods -A
docker compose ls
nvidia-smi
./ansible-run playbooks/health.yml
./ansible-run playbooks/validate.yml
```

## Documentation changes

Edit `docs/guide/*.md` and repository `docs/`, then run `scripts/render-glance-guide.py`; `config/glance/guide` is generated.

## WatooM Code package continuation

After package PASS, inspect the complete checkpoint and its gate. AUTO may continue dependency-ready packages in the same authorized milestone; MILESTONE leaves the next milestone PENDING and stops for explicit continuation. Background/child/recovery events do not authorize a new milestone. Stored sessions in the list are not active work; check `/api/session/active` before treating one as running.

## GPU and Mesh status

```bash
systemctl status watoom-gpu-controller.service watoom-opencode-mesh-bridge.service --no-pager
systemctl status watoom-gpu-controller-credentials.timer --no-pager
systemctl show watoom-llama-mesh-recovery.service -p ActiveState -p Result -p ExecMainStatus
kubectl -n llama-cpp get deployments
python3 scripts/verify-opencode-kali-security.py   # also confirms MCP connections
```

`watoom-llama-mesh-recovery.service` is a boot-time one-shot that reconciles the mesh job queue; it retries after a failed start (60 s, at most 5 starts in 15 min), so a boot race with k3s no longer leaves it failed. A manual `systemctl start` is safe when no job is running or pending. A host-wide out-of-memory event (the 20 Gi `llama-cpp` pod limit on a 31 GB host that also runs everything else) swaps the machine hard and can look like a hang; check `journalctl -k | grep -i oom` and `kubectl -n llama-cpp describe pod` (Last State OOMKilled).

Normal idle state: the selected backend ready, Mesh and other GPU candidates at zero, owner null, `qwen-ready` and uncertain false. A live Mesh owner is a legitimate transition; do not race it. Recovery oneshot inactive/success/exit 0 is healthy. Preserve receipts and journals; follow [Mesh recovery](LLAMA_MESH_WORKFLOW.md).

## Kali security isolation

Only `watoom-kali` can use the Kali MCP tools; the coordinator delegates Kali and Nmap work to it, and the owner can also start a `watoom-kali` session directly. Check the live rules with `python3 scripts/verify-opencode-kali-security.py`. Details: Kali security workflow.

### Rig access for the operator assistant

The lab server reaches the Windows rig (10.99.1.44) over two SSH routes on port 2224: the restricted `uemcp` ForceCommand account for ue-mcp (models and operator), and the key-only administrator account `migrate` for operator fixes (workers, Unreal, Godot, disk moves). Both accept only keys from this server; the private keys are in `/data/ai/ue-mcp-ssh/` and `/data/ai/rig-migrate-ssh/`. Setup and removal are in `tools/rig-ue-mcp/README.md` (`Add-RigMaintenanceAccount.ps1 -Remove`). When the Unreal editor is closed, `python3 tools/rig-ue-mcp/ue_route.py ensure` starts it and waits for the bridge (a cold start can take 12 minutes). The Epic vault cache lives on F: behind a junction; if C: fills up again check `C:\Users\RIG_USER\AppData\Local\UnrealEngine\Common\Zen` and the derived-data cache first.
