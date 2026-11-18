---
title: Troubleshooting
nav: Troubleshooting
summary: Symptom-first diagnostics. Collect evidence before restarting anything, and work from the lowest layer upward — network, DNS, node, route, service, application.
---

## Host or network unreachable

```bash
ip -br addr
ip route                         # default via 10.99.20.1 dev enp34s0.20
nmcli connection show --active
ping -c 4 10.99.20.1
```

The DMZ link `enp35s0` has a connected route only. A default route on it is a misconfiguration.

## Name does not resolve

```bash
dig +short <name>.internal.homelab.example @10.99.20.225        # Pi-hole
dig +short kubernetes.default.svc.cluster.local @10.243.0.10   # CoreDNS
kubectl -n pihole get pod -o wide
```

If Traefik has a route but Pi-hole returns nothing, add the local DNS record in Pi-hole. Never add `*.agent.example` overrides.

## HTTPS returns 404, 502 or 503

```bash
curl -skI --resolve <name>.internal.homelab.example:443:10.99.20.225 https://<name>.internal.homelab.example/
kubectl get ingressroute -A | grep <name>
kubectl -n <ns> get deploy,endpoints
```

| Status | Usual cause |
|---|---|
| 404 | No route matches the host or path prefix |
| 502 | The backend refused the connection: wrong port or not ready |
| 503 | Route matches but the Service has no endpoints (often an intentionally scaled-down app) |
| Certificate warning | Client does not trust the internal CA |

## Pod not starting

```bash
kubectl -n <ns> describe pod <pod> | sed -n '/Events/,$p'
kubectl -n <ns> logs <pod> --previous --tail=100
```

| Event | Check |
|---|---|
| `hostPath type check failed … is not a directory` | A mounted project or data path was moved or deleted. Restore it to that path (or update the owning manifest) rather than creating an empty directory |
| `Insufficient nvidia.com/gpu` | Another model holds the GPU. This is expected; the controller arbitrates |
| `Evicted` / disk pressure | `df -h / /app /data`; remove unused images explicitly |
| `ImagePullBackOff` for `127.0.0.1:5000/…` | `docker ps --filter name=watoom-local-registry` |

## Glance widget shows an error

```bash
kubectl -n glance logs deploy/glance -c glance --tail=100
kubectl -n glance logs deploy/glance -c helper-api --tail=100
kubectl -n glance exec deploy/glance -c helper-api -- \
  python3 -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:9000/<endpoint>').read()[:400])"
```

Helper endpoints return JSON. An `error` field names the upstream that failed. A rejected API key is reported as such and needs a new value in `glance-secrets`.

## AI request fails or stalls

```bash
cat /data/ai/helper-scripts/state/gpu-controller/state.json
systemctl status watoom-gpu-controller --no-pager
kubectl -n llama-cpp get deploy | awk '$2!="0/0"'
kubectl -n llama-cpp logs deploy/llm-router --tail=100
nvidia-smi
```

| Observation | Meaning |
|---|---|
| Target model `0/0` before a request | Normal; the controller starts it on demand |
| `owner` not null | A switch, Mesh job or operator task is running. Wait for it |
| `uncertain: true` | An interrupted transition. Use the controller's reconciliation, never manual scaling |
| CUDA out of memory | The model, context and KV profile exceed 20 GiB. Revisit the placement policy |

Do not restart a healthy controller, edit its state or scale model Deployments.

## WatooM Code job did not complete

1. Read the job's status file and the receipt it references before resubmitting. RIG jobs report in `<project>/.opencode/rig-worker-requests/<request>.status.json`. Duplicate submissions are refused by design.
2. For render and RIG jobs, check the broker queue state and the dispatcher journal: `journalctl -u watoom-rig-async-stage.service -n 50`.
3. For Toolkit jobs, check the worker pod in `watoom-code` and its output receipt.
4. Stored session history is not an active execution. Confirm active owners before interrupting anything.

## Stream or radio down

```bash
docker ps -a --filter name=stream- --filter name=cloudflared --filter name=azuracast
docker logs --tail=200 stream-app
docker logs --tail=100 cloudflared-stream
curl -sI http://10.99.20.225:8888/
```

Check Dispatcharr's source and HLS freshness before restarting the tunnel connector.

## Game server unreachable

1. Deployment running and ready (`kubectl -n <game> get deploy,pod`).
2. Service ports bound on the host (`ss -lunp | grep <port>`).
3. Reachable from the LAN on `10.99.20.225`.
4. Router dst-nat counters increase for the port.
5. Forward-chain counters; hairpin NAT only matters when testing via the public IP from inside.

## WireGuard fails remotely

```bash
ss -lunp | grep 51820
docker logs --tail=100 wg-easy
```

Then check router NAT for UDP 51820 and the peer's last handshake in the admin UI.

## Heavy WatooM Code work stays queued

Read the existing job status and request ID first. Bazzite is the first route for heavy Blender, conversion, Godot capture and declarative asset capture. `QUEUED` with an unreachable reason does not authorize a duplicate. Check the remote SSH reachability, staged runtime and free-RAM gate through the owning operator diagnostics. Once the recorded wait reaches 600 seconds, status may say `rig_eligible`; the agent can then submit the equivalent RIG request. The bridge cannot submit it automatically. Local fallback is opt-in and normally disabled because it reserves production GPU headroom.

If SSH exits 255, current status should report Bazzite unreachable rather than a missing toolkit. Godot capture requires the additive Xvfb/Mesa capture image; a missing image is a staging/preflight failure. A plain error string containing “OOM” does not prove memory exhaustion. If a capture deadline follows a script error, use the script error as the cause. Do not adjust memory or replay until the actual receipt/status identifies the failure stage.

On Bazzite, the rootless Podman user service must not set `PrivateDevices=yes` or `NoNewPrivileges=yes`; either can block `newuidmap` when a fresh helper process is needed. Intermittent `unable to create a new pause process ... Operation not permitted` points to that user-unit restriction. Wi-Fi power-save can also produce high latency/dropouts and requests that remain queued with unreachable reasons; check the network path and power-save state before changing worker limits. The owning sources are `tools/watoom-code/bazzite_wait.py`, worker scripts under `tools/watoom-code/`, `tools/bazzite-render-worker/`, and the Bazzite unit configuration.

## MetaHuman export or RIG skin job fails

Separate the geometry and skin stages. Geometry export uses the full Unreal Editor and an 8 GiB Bazzite job; a commandlet Slate assertion is the wrong execution path. A shutdown crash can be accepted only when the native export result itself verifies as passed. The DCC skin stage requires a real GPU renderer because Epic TextureGraph does not complete headlessly; use the fixed `metahuman-skin` RIG operation. The tested 12 GiB Job Object limit was insufficient and failed with commit exhaustion/D3D12 E_OUTOFMEMORY; check the installed worker setting (read at worker start) and available RAM/disk before retrying. The engine's MetaHuman optional content must also be installed. Follow the existing job ID and collect/reconcile evidence instead of resubmitting. Source and limits are in the [extension guide](llm-extensions.md#metahuman-package-conversion) and RIG lane README.

## Language reference note missing or unhelpful

Check `wlk_status` for card-load and vector errors, and confirm the deployed plugin package and configured card path. Lexical lookup does not require the optional embedding service; vector search does. The live production dataset covers Godot and Blender, but a card is versioned (Godot 4.7.2, Blender 5.2.3): a differing tool version is flagged, not silently used. Triggers recognize only supported error patterns and uncertainty near API-looking names, and only insert an answer when a card can support it. Unit tests plus simulated plugin-context exercise are not evidence of a live-session trigger; verify an actual session before claiming that behavior is operational.


## AgentMemory is slow, saves are refused ("workflow backpressure"), memory says "delivery uncertain"
Seen 2026-11-16 (ticket T-0046). Symptoms: `/remember` returns "saved locally; AgentMemory delivery uncertain" or the app answers 500 with `workflow backpressure` in its log; `kubectl -n watoom-code logs deploy/agentmemory` shows `supersession candidate lookup failed ... Invocation timeout after 180000ms: state::list` and `[iii] Reconnecting` every 3 minutes; `[agentmemory] vector-index add batch: embed failed ... fetch failed`.

1. **Size of the store.** `du -sh /data/ai/watoom-code/memory/state_store.db/mem%3Amemories.bin` and count entries from the REST list (`/agentmemory/memories?latest=true`, `total`). The file-based store keeps each collection as one blob and a full list must finish inside 180 s: at 56,810 entries / 107 MB it never did, so the search index could not become ready and every save did two full scans. A healthy store is a few MB.
2. **What fills it.** The app records every session event as a `kind: checkpoint` memory (job `ses_<id>[:child]:evt_<id>`). `/data/github/watoom-standardised-homelab/standardised_k3s_project/tools/agentmemory/prune_checkpoints.js` (CronJob `agentmemory-retention`, hourly, `manifests/10-infrastructure/llm/agentmemory-retention.yml`) deletes those older than `RETENTION_HOURS` (12); explicit `/remember` saves, knowledge revisions, completions and compactions are kept. Run `kubectl -n watoom-code create job --from=cronjob/agentmemory-retention x` and read its log (`DRY_RUN=1` only counts).
3. **Shrinking a store that is already huge.** Deleting one by one costs O(store size) per delete (3.3 s each at 100 MB: days). Instead: back up `/data/ai/watoom-code/memory`; scale a scratch copy of the Deployment (same image, hostPath on a copy of the data) up; `POST /agentmemory/import` `{"exportData":{"version":"0.9.29","sessions":[],"observations":{},"memories":[<keepers>],"summaries":[],"accessLogs":[]},"strategy":"merge"}` into an EMPTY data dir (1,500 memories took 45 s); verify every kept record is identical; scale production to 0, replace only `mem%3Amemories.bin`, delete `mem%3Aindex*`, scale to 1. Never hand-edit the `.bin` files: the trailer is not a plain length. `mv` and `cp` are interactive aliases here: use `/bin/mv -f`.
4. **Embeddings.** `kubectl -n watoom-code exec deploy/agentmemory -- node -e "fetch('http://bge-embeddings.llama-cpp.svc.cluster.local:8000/v1/models').then(r=>console.log(r.status))"` must not say ECONNREFUSED. The ingress policy `bge-embeddings-clients` (in `manifests/10-infrastructure/llm/llama-cpp-network-policy.yml`) must name namespace `watoom-code`, not the retired `opencode-watoom-stage`.
5. **Stranded outbox.** The app marks an item `uncertain` when delivery times out (1 s) and refuses new explicit saves while more than 128 outbox items are unresolved. After the store is healthy run `tools/watoom-code/memory_outbox.py --evidence DIR --apply --i-approve` (items AgentMemory confirms become observed; the rest become pending). Pending items are delivered by the app, 32 per processed session event (a session created, a tool call, a step ended), so an idle system does not drain: create empty sessions in a hidden validation directory until `SELECT count(*) FROM _watoom_outbox WHERE state IN ('pending','sending','uncertain')` is under 128. **Draining re-delivers the old event telemetry into the store** (2026-11-16: 10,000 items took the 1.5 MB store back to 22 MB and the list failed again with `Invocation stopped` in under a second, on a copy too, so it is not load: a list of that size is refused, plausibly over the engine's message size). If that happens, rebuild again exactly as in step 3, but read the backed-up `mem%3Amemories.bin` offline instead of listing (it begins with one JSON object `{id: memory}`: `json.JSONDecoder().raw_decode(open(f,'rb').read().decode('utf-8','ignore'))[0]`), keep everything the retention classifier does not call telemetry, import that into an empty scratch instance and swap the file in. The CronJob keeps `RETENTION_HOURS` at 6 so the live store stays a few MB. This is also what blocks `deploy-platform.py`, whose fixture does a `/remember`.
