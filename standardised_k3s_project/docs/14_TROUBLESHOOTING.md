# Troubleshooting

Current deployment snapshot: 13 October 2026. Runtime-specific status is dated; configured/recovery guidance is not an end-to-end test.

Use evidence before restart. Work from the lowest relevant layer upward.

## Host unreachable / networking

```bash
ip -br addr
ip route
nmcli connection show --active
ping -c 4 10.99.20.1
```

Expected host routing includes default via `10.99.20.1` on `enp34s0.20` and a connected DMZ route on `enp35s0`.

## Internal DNS failure

```bash
dig @10.99.20.225 glance.internal.homelab.example
dig @10.243.0.10 kubernetes.default.svc.cluster.local
kubectl -n pihole get pod,svc
```

Do not reintroduce `.agent.example` overrides to solve an `internal.homelab.example` problem.

## k3s node or pod issue

```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl describe node watoom-homelab
kubectl -n <ns> get events --sort-by=.lastTimestamp
kubectl -n <ns> logs deploy/<name> --tail=200
```

Check root filesystem pressure because `/var/lib/rancher/k3s` has historically been a large root consumer.

## Internal HTTPS 404 / 502

```bash
kubectl -n kube-system get deploy,svc | grep traefik
kubectl get ingressroute -A 2>/dev/null || true
curl -kI --resolve glance.internal.homelab.example:443:10.99.20.225   https://glance.internal.homelab.example/
```

A 404 usually points to route matching; a 502 more often points to backend/service readiness or port mismatch.

## Docker stream unavailable

Check in this order:

```bash
docker ps -a --filter name=stream-
docker logs --tail=200 stream-app
docker logs --tail=200 stream-nginx
docker logs --tail=200 cloudflared-stream
curl -I http://10.99.20.225:8888/
```

Also verify Dispatcharr's source/M3U and HLS segment freshness before restarting the Cloudflare connector.

## Psytrance unavailable

```bash
docker ps -a --filter name=azuracast --filter name=cloudflared-psytrance
docker logs --tail=200 azuracast
docker logs --tail=200 cloudflared-psytrance
```

## Game server unreachable

1. Check deployment replicas/readiness.
2. Check Service ports/external IPs.
3. Test LAN and DMZ address locally.
4. Check router dstnat counters.
5. Check forward counters and hairpin only if local-public-IP access is relevant.

## WireGuard fails remotely

```bash
ss -lunp | grep 51820
docker ps --filter name=wg-easy
docker logs --tail=200 wg-easy
```

Then verify router NAT for UDP 51820 and peer state. Do not restore `/app/openvpn`.

## LLM request fails

```bash
kubectl -n llama-cpp get deploy,pod,svc
kubectl -n llama-cpp logs deploy/llm-router --tail=200
kubectl -n open-webui get pod
kubectl -n searxng get pod
nvidia-smi
```

Interpretation:

- target model 0/0 before request can be normal;
- router requests authorised transitions through the controller and waits for `/health`; direct scaling is prohibited;
- CUDA OOM/GPU instability requires checking the selected model/context against 20 GB VRAM;
- an old `qwen38` direct ingress is not evidence that it is part of the current visible router model set.

## OpenCode unexpected continuation

Collect active ownership from every OpenCode server process, persisted inbox/pending/suspended state, child IDs and progress checkpoints before changing behavior. Stored session history is not an active execution. Check for a secondary CLI background server sharing the same database. Its relationship to the previous duplicate-P2 incident remains a hypothesis until a correlated reproduction and reversible positive control establish it. Avoid direct database edits or broad cleanup during diagnosis.

## Mesh unavailable or GPU owned

Read controller durable status and worker liveness before recovery. A live or uncertain owner must fail closed; do not restart a healthy controller, edit ownership or force replicas. Reuse the original Mesh request ID after an uncertain result and inspect its job/receipt rather than creating a second job.

Check controller, bridge, credential timer and the recovery oneshot as described in [operations](13_OPERATIONS_RUNBOOK.md). Inactive recovery with success/exit 0 is normal. Use the authenticated OpenCode API for MCP connection status; an unauthenticated 401 or bare CLI's empty MCP list does not prove production registration is broken.

Stale GUI profile names and the router's 32K label are not backend context evidence. Current Swift backend is 131072/Q4 KV; OpenCode has separate provider budgets. Inspect live Deployment settings and [AI platform](09_LLM_AI_PLATFORM.md).
