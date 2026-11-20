import os, json, re, time, html, hmac, hashlib, secrets, urllib.request, urllib.parse, urllib.error, mimetypes
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

GRAFANA="http://grafana.monitoring.svc.cluster.local:3000"
PROM="http://prometheus.monitoring.svc.cluster.local:9090"
SEARXNG="http://searxng.searxng.svc.cluster.local:8080"
LLM_ROUTER=os.environ.get("CC_LLM_ROUTER_URL", "http://llm-router.llama-cpp.svc.cluster.local:8000")

GUIDE_ROOT=Path(os.environ.get("GLANCE_GUIDE_ROOT","/app/guide")).resolve()

CACHE={}
def cached(key, ttl, fn):
  now=datetime.now(timezone.utc).timestamp()
  hit=CACHE.get(key)
  if hit and now-hit["time"] < ttl:
    return hit["data"]
  data=fn()
  CACHE[key]={"time":now,"data":data}
  return data



def get_json(url, headers=None, timeout=3):
  req = urllib.request.Request(url, headers=headers or {})
  with urllib.request.urlopen(req, timeout=timeout) as r:
    return json.loads(r.read().decode("utf-8", "replace"))

def try_json(url, headers=None, timeout=3):
  try:
    return get_json(url, headers, timeout), ""
  except Exception as e:
    return None, str(e)














def first_prom_value(query, default=0):
  data = get_json(f"{PROM}/api/v1/query?query={urllib.parse.quote(query)}")
  result = data.get("data", {}).get("result", [])
  if not result:
    return default
  try:
    return float(result[0].get("value", [0, default])[1])
  except Exception:
    return default


def prom_vector(query):
  try:
    data = get_json(f"{PROM}/api/v1/query?query={urllib.parse.quote(query)}")
    return data.get("data", {}).get("result", [])
  except Exception:
    return []

def prom_namespace_values(query):
  out={}
  for row in prom_vector(query):
    ns=row.get("metric", {}).get("namespace", "unknown")
    try:
      out[ns]=float(row.get("value", [0, 0])[1])
    except Exception:
      out[ns]=0
  return out

def fmt_bytes(value):
  value = float(value or 0)
  units = ["B", "KiB", "MiB", "GiB", "TiB"]
  i = 0
  while value >= 1024 and i < len(units) - 1:
    value /= 1024
    i += 1
  return f"{value:.1f} {units[i]}"

def app_summary(name, data, err, primary, secondary=""):
  return {
    "name": name,
    "status": "error" if err else "ok",
    "primary": primary if not err else "API error",
    "secondary": secondary if not err else err,
  }



def stats():
  grafana, grafana_err = try_json(f"{GRAFANA}/api/health")

  node_ready = first_prom_value('up{job="node-exporter"}', 0)
  prom_ready = first_prom_value('up{job="prometheus"}', 0)
  total_mem = first_prom_value('node_memory_MemTotal_bytes', 0)
  avail_mem = first_prom_value('node_memory_MemAvailable_bytes', 0)
  cpu_count = first_prom_value('count(count by (cpu) (node_cpu_seconds_total{mode="idle"}))', 0)
  root_avail = first_prom_value('node_filesystem_avail_bytes{mountpoint="/",fstype!="rootfs"}', 0)
  root_size = first_prom_value('node_filesystem_size_bytes{mountpoint="/",fstype!="rootfs"}', 0)
  pods_running = first_prom_value('sum(kube_pod_status_phase{phase="Running"})', 0)
  pods_pending = first_prom_value('sum(kube_pod_status_phase{phase="Pending"})', 0)
  pods_failed = first_prom_value('sum(kube_pod_status_phase{phase="Failed"})', 0)
  deploy_unavailable = first_prom_value('sum(kube_deployment_status_replicas_unavailable)', 0)

  apps = [
    app_summary("Grafana", grafana, grafana_err, (grafana or {}).get("database", "unknown"), (grafana or {}).get("version", "")),
  ]

  issues=[a for a in apps if a.get("status") != "ok"]

  mem_used_pct = round(((total_mem - avail_mem) / total_mem) * 100, 1) if total_mem else 0
  disk_used_pct = round(((root_size - root_avail) / root_size) * 100, 1) if root_size else 0

  return {
    "summary": {
      "apps_total": len(apps),
      "apps_ok": len(apps) - len(issues),
      "apps_error": len(issues),
      "issues": issues[:6],
    },
    "apps": apps,
    "cluster": {
      "node_exporter": "up" if node_ready == 1 else "down",
      "prometheus": "up" if prom_ready == 1 else "down",
      "cpu_cores": int(cpu_count),
      "memory_used_pct": mem_used_pct,
      "memory_available": fmt_bytes(avail_mem),
      "disk_used_pct": disk_used_pct,
      "disk_available": fmt_bytes(root_avail),
      "pods_running": int(pods_running),
      "pods_pending": int(pods_pending),
      "pods_failed": int(pods_failed),
      "deployments_unavailable": int(deploy_unavailable),
    }
  }

def k3s_metrics():
  return stats()["cluster"]

def cluster_detail():
  cluster=stats()["cluster"]
  running=prom_namespace_values('sum by(namespace) (kube_pod_status_phase{phase="Running"})')
  pending=prom_namespace_values('sum by(namespace) (kube_pod_status_phase{phase="Pending"})')
  failed=prom_namespace_values('sum by(namespace) (kube_pod_status_phase{phase="Failed"})')
  succeeded=prom_namespace_values('sum by(namespace) (kube_pod_status_phase{phase="Succeeded"})')
  desired=prom_namespace_values('sum by(namespace) (kube_deployment_spec_replicas)')
  available=prom_namespace_values('sum by(namespace) (kube_deployment_status_replicas_available)')
  unavailable=prom_namespace_values('sum by(namespace) (kube_deployment_status_replicas_unavailable)')
  restarts=prom_namespace_values('sum by(namespace) (kube_pod_container_status_restarts_total)')

  namespaces=[]
  for ns in sorted(set(running) | set(pending) | set(failed) | set(succeeded) | set(desired) | set(available) | set(unavailable) | set(restarts)):
    item={
      "namespace":ns,
      "running":int(running.get(ns,0)),
      "pending":int(pending.get(ns,0)),
      "failed":int(failed.get(ns,0)),
      "succeeded":int(succeeded.get(ns,0)),
      "desired":int(desired.get(ns,0)),
      "available":int(available.get(ns,0)),
      "unavailable":int(unavailable.get(ns,0)),
      "restarts":int(restarts.get(ns,0)),
    }
    item["status"]="warn" if item["pending"] or item["failed"] or item["unavailable"] else "ok"
    namespaces.append(item)

  namespaces=sorted(namespaces, key=lambda x: (x["status"] != "warn", -(x["pending"] + x["failed"] + x["unavailable"]), -x["running"], x["namespace"]))

  phases=[]
  for phase in ["Running","Pending","Failed","Succeeded","Unknown"]:
    phases.append({"phase":phase,"count":int(first_prom_value(f'sum(kube_pod_status_phase{{phase="{phase}"}})', 0))})

  restart_hotspots=[]
  for row in prom_vector('topk(8, kube_pod_container_status_restarts_total)'):
    metric=row.get("metric", {})
    try:
      count=int(float(row.get("value", [0, 0])[1]))
    except Exception:
      count=0
    if count <= 0:
      continue
    restart_hotspots.append({
      "namespace":metric.get("namespace", ""),
      "pod":metric.get("pod", ""),
      "container":metric.get("container", ""),
      "restarts":count,
    })

  return {
    "cluster":cluster,
    "namespaces":namespaces[:30],
    "problem_namespaces":[x for x in namespaces if x["status"] == "warn"][:10],
    "pod_phases":phases,
    "restart_hotspots":restart_hotspots,
  }
























def http_health(name, url, primary="ready", timeout=2):
  try:
    with urllib.request.urlopen(url, timeout=timeout) as r:
      return {
        "name": name,
        "status": "ok" if 200 <= r.status < 400 else "error",
        "primary": primary if 200 <= r.status < 400 else "unavailable",
        "secondary": f"HTTP {r.status}",
      }
  except Exception as e:
    return {
      "name": name,
      "status": "error",
      "primary": "unavailable",
      "secondary": str(e)[:120],
    }

def llm_summary():
  services=[
    http_health("WatooM Code", "http://watoom-code.watoom-code.svc.cluster.local:4096", "GUI responding"),
    http_health("Swift / Qwen", "http://llama-cpp-swift-qwen38-coder.llama-cpp.svc.cluster.local:8000/health", "model ready"),
    http_health("SearXNG", f"{SEARXNG}/healthz", "search ready"),
  ]
  ok=sum(1 for s in services if s["status"]=="ok")
  return {"generated_at":datetime.now(timezone.utc).isoformat(),
    "summary":{"ok":ok,"total":len(services),"errors":len(services)-ok},
    "services":services,"models":{"primary":"Swift-Qwen3.8-27B","application_context":100000},
    "links":{"watoom_code":"https://watoom-code.internal.homelab.example","searxng":"https://searxng.internal.homelab.example"}}




# ---------------------------------------------------------------------------
# Command center: one unified homelab view (live metrics, service topology and
# WAN scan-origin aggregation). Every function fails soft to empty/last-good so
# the page never hard-errors. Queries mirror the owner's Grafana dashboards.
# ---------------------------------------------------------------------------
LOKI = "http://loki.monitoring.svc.cluster.local:3100"
CC_DIR = Path(os.environ.get("CC_ASSET_ROOT", "/app/command-center")).resolve()
PUBLIC_IP = os.environ.get("CC_PUBLIC_IP", "")  # display only; parsed from drops if unset


def loki_range(query, limit=1500, hours=6):
  end = int(datetime.now(timezone.utc).timestamp() * 1e9)
  start = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp() * 1e9)
  url = (f"{LOKI}/loki/api/v1/query_range?query={urllib.parse.quote(query)}"
         f"&limit={limit}&start={start}&end={end}&direction=backward")
  return get_json(url, timeout=6)


def cc_gpu():
  used = first_prom_value('max(DCGM_FI_DEV_FB_USED)', 0)   # MiB
  free = first_prom_value('max(DCGM_FI_DEV_FB_FREE)', 0)   # MiB
  total = used + free
  return {
    "present": total > 0,
    "util_pct": round(first_prom_value('max(DCGM_FI_DEV_GPU_UTIL)', 0)),
    "temp_c": round(first_prom_value('max(DCGM_FI_DEV_GPU_TEMP)', 0)),
    "power_w": round(first_prom_value('max(DCGM_FI_DEV_POWER_USAGE)', 0)),
    "mem_copy_pct": round(first_prom_value('max(DCGM_FI_DEV_MEM_COPY_UTIL)', 0)),
    "mem_used_mib": round(used),
    "mem_total_mib": round(total),
    "mem_used_pct": round(used / total * 100, 1) if total else 0,
  }


CC_WAN_IFACE = os.environ.get("CC_WAN_IFACE", "wan-uplink")


def cc_wan():
  # mktxp interface counters -> bits/sec. A 5m rate window tolerates mktxp's slow
  # scrape (a 1m window often lacks two samples). Fails soft to present:false.
  sel = '{name="%s"}' % CC_WAN_IFACE
  rx = first_prom_value('sum(rate(mktxp_interface_rx_byte_total%s[5m])) * 8' % sel, 0)
  tx = first_prom_value('sum(rate(mktxp_interface_tx_byte_total%s[5m])) * 8' % sel, 0)
  drops = first_prom_value('sum(rate(mktxp_interface_rx_drop_total%s[5m]))' % sel, 0)
  router_cpu = first_prom_value('max(mktxp_system_cpu_load)', 0)
  return {
    "present": (rx + tx) > 0 or router_cpu > 0,
    "rx_bps": round(rx), "tx_bps": round(tx),
    "rx_human": fmt_bytes(rx / 8) + "/s", "tx_human": fmt_bytes(tx / 8) + "/s",
    "wan_drops_per_s": round(drops, 2),
    "router_cpu_pct": round(router_cpu),
  }


def _prom_by_model(query):
  # Collapse a Prometheus vector to {model_label: float}.
  out = {}
  for row in prom_vector(query):
    m = row.get("metric", {}).get("model")
    if not m:
      continue
    try:
      out[m] = float(row.get("value", [0, 0])[1])
    except Exception:
      pass
  return out


# Serving models surfaced on the command center LLM panel, in display order.
CC_LLM_MODELS = [m for m in os.environ.get(
    "CC_LLM_MODELS",
    "swift-qwen38-coder,qwen38-uncensored-mtp,tiel-coder-35b-a3b-mtp,ornith-15-9b").split(",") if m]


def cc_llm():
  # llama.cpp + llm-router serving telemetry. The single 20 GiB GPU holds one
  # backend at a time (the lease owner is "up"); the others report last-known
  # throughput from llama-perf. All queries fail soft to present:false.
  up = _prom_by_model('max by (model) (up{job="llama-cpp"})')
  slots = _prom_by_model('sum by (model) (watoom_llama_slot_active)')
  tps = _prom_by_model('sum by (model) (llama_perf_generated_tokens_per_second{job="llama-perf"})')
  ctx = _prom_by_model('max by (model) (llamacpp:n_tokens_max{job="llama-cpp"})')
  mtp = _prom_by_model('max by (model) (watoom_llama_slot_last_mtp_acceptance_ratio)')
  # A model earns a row only if it carries real signal (perf samples) or is the
  # current GPU owner; the curated roster is always shown. This drops the many
  # defined-but-idle backends that only expose a flat up=0 series.
  signal = set(tps) | set(ctx) | set(mtp)
  up_models = {m for m, v in up.items() if v >= 1}
  show = signal | up_models | set(CC_LLM_MODELS)
  active = next(iter(up_models), None)
  models, seen = [], set()
  for m in CC_LLM_MODELS + sorted(show - set(CC_LLM_MODELS)):
    if m in seen or m not in show:
      continue
    seen.add(m)
    models.append({
      "model": m,
      "up": up.get(m, 0) >= 1,
      "slots": round(slots.get(m, 0)),
      "gen_tps": round(tps.get(m, 0), 1) if m in tps else None,
      "ctx_max": round(ctx.get(m, 0)) if m in ctx else None,
      "mtp_accept_pct": round(mtp.get(m, 0) * 100) if m in mtp else None,
    })
  return {
    "present": bool(signal or up_models),
    "active_model": active,
    "requests_processing": round(first_prom_value('sum(llamacpp:requests_processing{job="llama-cpp"})', 0)),
    "requests_deferred": round(first_prom_value('sum(llamacpp:requests_deferred{job="llama-cpp"})', 0)),
    "router_req_30m": round(first_prom_value('sum(increase(watoom_llm_router_requests_total[30m]))', 0)),
    "router_fail_30m": round(first_prom_value('sum(increase(watoom_llm_router_failures_total[30m]))', 0)),
    "models": models,
  }


CC_WORKER_FILE = os.environ.get("WORKER_STATUS_FILE", "/app/worker-status/workers.json")
CC_WORKER_STALE_S = 120
CC_MEDIA_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".mp4": "video/mp4", ".webm": "video/webm", ".glb": "model/gltf-binary"}
CC_MEDIA_NAME = re.compile(r"^[A-Za-z0-9._-]{1,64}/[A-Za-z0-9._-]{1,64}$")
CC_MEDIA_MAX = 40 * 1024 * 1024   # the container holds a served file in memory: keep this well under its 320 MiB limit


def cc_workers():
  # Bazzite / RIG worker activity and job outcomes. A root collector on the host (tools/watoom-code/worker_status.py) writes a sanitised
  # snapshot every ~30 s; this only reads it. Fails soft: no file -> present:false, an old file -> stale:true (the page says so).
  try:
    with open(CC_WORKER_FILE, "rb") as fh:
      data = json.loads(fh.read(2_000_000))
  except (OSError, ValueError):
    return {"present": False}
  if not isinstance(data, dict) or data.get("schema") != 1:
    return {"present": False}
  now = time.time()
  age = max(0, now - float(data.get("generated") or 0))
  data.update({"present": True, "now": now, "age_s": round(age), "stale": age > CC_WORKER_STALE_S})
  return data


# ---- host change requests: the page reads a published feed and queues a PIN-protected decision for the root scanner ----
CR_STATE = Path(os.environ.get("CC_CR_STATE", "/app/change-requests"))
CR_PIN = os.environ.get("CC_CR_PIN_HASH", "")   # "salt_hex:pbkdf2_sha256_hex" of the operator PIN; empty disables approving
CR_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
CR_SHA = re.compile(r"[0-9a-f]{64}")
cr_fail = {"n": 0, "until": 0.0}

def cc_change_requests():
  try:
    data = json.loads((CR_STATE / "requests.json").read_text())
    if not isinstance(data, dict) or not isinstance(data.get("requests"), list):
      return {"present": False}
    data["present"] = True
    data["age_s"] = max(0, int(time.time() - float(data.get("generated", 0))))
    data["approval_enabled"] = bool(CR_PIN)
    return data
  except (OSError, ValueError):
    return {"present": False}

def cr_pin_ok(pin):
  if not CR_PIN or ":" not in CR_PIN or not isinstance(pin, str) or not 8 <= len(pin) <= 128:
    return False
  salt, want = CR_PIN.split(":", 1)
  got = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200000).hex()
  return hmac.compare_digest(got, want)

def cr_decide(body, client):
  """Validate a decision and drop it for the host scanner. Returns (status, message)."""
  now = time.time()
  if now < cr_fail["until"]:
    return 429, "Too many wrong PINs; try again in a few minutes."
  if not CR_PIN:
    return 503, "Approving from Glance is not configured (no operator PIN set)."
  if not isinstance(body, dict) or body.get("action") not in ("approve", "reject"):
    return 400, "Invalid request."
  rid, project, sha = body.get("id"), body.get("project"), body.get("request_sha256")
  if not (isinstance(rid, str) and CR_ID.fullmatch(rid) and isinstance(project, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,80}", project) and isinstance(sha, str) and CR_SHA.fullmatch(sha)):
    return 400, "Invalid request."
  if not cr_pin_ok(body.get("pin")):
    cr_fail["n"] += 1
    if cr_fail["n"] >= 5:
      cr_fail["n"], cr_fail["until"] = 0, now + 300
    return 403, "Wrong PIN."
  cr_fail["n"] = 0
  feed = cc_change_requests()
  live = next((r for r in feed.get("requests", []) if r.get("id") == rid and r.get("project") == project), None)
  if not live or live.get("status") != "PENDING_APPROVAL" or live.get("request_sha256") != sha:
    return 409, "That request is no longer pending in the version you reviewed. Reload the page."
  inbox = CR_STATE / "decisions"
  inbox.mkdir(parents=True, exist_ok=True)
  name = "%d-%s.json" % (int(now), secrets.token_hex(4))
  tmp = inbox / ("." + name)
  tmp.write_text(json.dumps({"action": body["action"], "id": rid, "project": project, "request_sha256": sha, "client": client, "time": now}))
  os.replace(tmp, inbox / name)
  return 202, "Queued. The host applies it within about a minute; this page updates when it does."

# ---- break-glass: PIN-protected request for the host recovery service (tools/break-glass/break_glass.py) ----
BG_STATE = Path(os.environ.get("CC_BG_STATE", "/app/break-glass"))
BG_MODES = ("stale", "force")

def cc_break_glass():
  try:
    data = json.loads((BG_STATE / "status.json").read_text())
    if not isinstance(data, dict):
      return {"present": False}
    data["present"] = True
    data["age_s"] = max(0, int(time.time() - float(data.get("generated", 0))))
    data["approval_enabled"] = bool(CR_PIN)
    data["queued"] = len(list((BG_STATE / "inbox").glob("*.json"))) if (BG_STATE / "inbox").is_dir() else 0
    return data
  except (OSError, ValueError):
    return {"present": False}

def bg_request(body, client):
  """Validate a break-glass request and drop it for the root service. Returns (status, message)."""
  now = time.time()
  if now < cr_fail["until"]:
    return 429, "Too many wrong PINs; try again in a few minutes."
  if not CR_PIN:
    return 503, "Break-glass from Glance is not configured (no operator PIN set)."
  if not isinstance(body, dict) or body.get("mode") not in BG_MODES:
    return 400, "Invalid request."
  if not cr_pin_ok(body.get("pin")):
    cr_fail["n"] += 1
    if cr_fail["n"] >= 5:
      cr_fail["n"], cr_fail["until"] = 0, now + 300
    return 403, "Wrong PIN."
  cr_fail["n"] = 0
  if body["mode"] == "force" and body.get("confirm") != "RESET":
    return 400, "Type RESET to confirm a force reset."
  inbox = BG_STATE / "inbox"
  queued = len(list(inbox.glob("*.json"))) if inbox.is_dir() else 0
  if queued or cc_break_glass().get("running"):
    return 409, "A recovery run is already queued or running."
  inbox.mkdir(parents=True, exist_ok=True)
  name = "%d-%s.json" % (int(now), secrets.token_hex(4))
  tmp = inbox / ("." + name)
  tmp.write_text(json.dumps({"mode": body["mode"], "time": now, "client": client}))
  os.replace(tmp, inbox / name)
  return 202, "Queued. The host starts it within seconds; progress appears below."

def cc_llm_performance():
  # Router-side rolling request observations are the only source with reasoning_effort labels.
  try:
    with urllib.request.urlopen(LLM_ROUTER + "/performance", timeout=4) as response:
      data = json.loads(response.read(262144))
    if not isinstance(data, dict) or not isinstance(data.get("levels"), dict):
      return {"present": False}
    data["present"] = True
    return data
  except (OSError, ValueError, urllib.error.URLError):
    return {"present": False}


def cc_metrics():
  st = stats()
  cl = st["cluster"]
  load1 = first_prom_value('node_load1', 0)
  uptime_s = first_prom_value('time() - node_boot_time_seconds', 0)
  dev = 'device!~"lo|veth.*|cni.*|flannel.*|docker.*|br-.*"'
  net_rx = first_prom_value('sum(rate(node_network_receive_bytes_total{%s}[5m]))*8' % dev, 0)
  net_tx = first_prom_value('sum(rate(node_network_transmit_bytes_total{%s}[5m]))*8' % dev, 0)
  return {
    "ts": datetime.now(timezone.utc).isoformat(),
    "host": {
      "cpu_cores": cl["cpu_cores"],
      "load1": round(load1, 2),
      "cpu_pct": round(min(100.0, (load1 / cl["cpu_cores"] * 100) if cl["cpu_cores"] else 0), 1),
      "mem_used_pct": cl["memory_used_pct"], "mem_available": cl["memory_available"],
      "disk_used_pct": cl["disk_used_pct"], "disk_available": cl["disk_available"],
      "node_exporter": cl["node_exporter"], "prometheus": cl["prometheus"],
      "uptime_s": round(uptime_s),
      "net_rx_human": fmt_bytes(net_rx / 8) + "/s", "net_tx_human": fmt_bytes(net_tx / 8) + "/s",
    },
    "k3s": {
      "pods_running": cl["pods_running"], "pods_pending": cl["pods_pending"],
      "pods_failed": cl["pods_failed"], "deployments_unavailable": cl["deployments_unavailable"],
    },
    "gpu": cc_gpu(),
    "wan": cc_wan(),
    "llm": cc_llm(),
    "services": {"total": st["summary"]["apps_total"], "ok": st["summary"]["apps_ok"],
                 "error": st["summary"]["apps_error"], "issues": st["summary"]["issues"]},
  }


# Service tiers for the dataflow topology. Each group maps to namespaces whose
# pod health rolls up from cluster_detail(); edges describe data/control flow.
CC_TIERS = [
  ("wan", "WAN / Internet", []),
  ("edge", "Router + Firewall", []),
  ("ingress", "Traefik Ingress", ["kube-system"]),
  ("llm", "LLM / Agents", ["llama-cpp", "watoom-code", "ollama", "open-webui"]),
  ("platform", "Platform", ["glance", "platform-workers"]),
  ("observability", "Observability", ["monitoring"]),
]
CC_EDGES = [("wan", "edge"), ("edge", "ingress"), ("ingress", "llm"),
            ("ingress", "platform"), ("edge", "platform"), ("llm", "observability"), ("platform", "observability"), ("ingress", "observability")]


def cc_topology():
  detail = cluster_detail()
  by_ns = {n["namespace"]: n for n in detail["namespaces"]}
  attacks = cached("cc-attacks", 60, cc_attacks)
  nodes = []
  for tid, label, namespaces in CC_TIERS:
    running = pending = failed = restarts = 0
    for ns in namespaces:
      n = by_ns.get(ns)
      if n:
        running += n["running"]; pending += n["pending"]; failed += n["failed"]; restarts += n["restarts"]
    status = "ok"
    detail_txt = ""
    if tid == "wan":
      status = "warn" if attacks.get("total_events", 0) else "ok"
      detail_txt = f"{attacks.get('total_events', 0)} drops/{attacks.get('window_hours', 6)}h"
    elif tid == "edge":
      wan = cached("cc-metrics", 15, cc_metrics).get("wan", {})
      status = "ok" if wan.get("present") else "warn"
      detail_txt = f"{wan.get('rx_human', '-')} in"
    elif namespaces:
      status = "bad" if failed else ("warn" if pending else "ok")
      detail_txt = f"{running} pods" + (f" · {restarts} restarts" if restarts else "")
    nodes.append({"id": tid, "label": label, "status": status, "detail": detail_txt,
                  "running": running, "pending": pending, "failed": failed})
  edges = []
  for src, dst in CC_EDGES:
    sev = "error" if src == "wan" and attacks.get("total_events", 0) else "flow"
    edges.append({"from": src, "to": dst, "severity": sev})
  return {"nodes": nodes, "edges": edges, "ts": datetime.now(timezone.utc).isoformat()}


# --- WAN scan-origin aggregation (GeoIP is offline/vendored; absent => no map) --
_GEO = {"loaded": False, "v4": None, "cc": {}}
_DROP_RE = re.compile(r'(\d{1,3}(?:\.\d{1,3}){3}):\d+->(\d{1,3}(?:\.\d{1,3}){3}):\d+')
_PREFIX_RE = re.compile(r'firewall,\w+\s+(\S+)')


def _ip4_int(ip):
  try:
    a, b, c, d = (int(x) for x in ip.split("."))
    return (a << 24) | (b << 16) | (c << 8) | d
  except Exception:
    return None


# RFC1918 / loopback / link-local / CGNAT ranges, as (network, mask) on 32-bit ints.
_PRIVATE_NETS = (
  (0x0A000000, 0xFF000000),  # 10.0.0.0/8
  (0xAC100000, 0xFFF00000),  # 172.16.0.0/12  (covers 172.16-172.31)
  (0xC0A80000, 0xFFFF0000),  # 192.168.250.0/16
  (0x7F000000, 0xFF000000),  # 127.0.0.0/8
  (0xA9FE0000, 0xFFFF0000),  # 169.254.0.0/16
  (0x64400000, 0xFFC00000),  # 100.64.0.0/10  (CGNAT)
)


def _is_private(ip):
  n = _ip4_int(ip)
  if n is None:
    return True  # unparseable -> treat as noise, skip
  return any((n & mask) == net for net, mask in _PRIVATE_NETS)


def _load_geo():
  # ipv4-country.bin: sorted records of >IIH (start, end, country_index);
  # countries.json: ["CC", lat, lon, "Name"] list indexed by that country_index.
  if _GEO["loaded"]:
    return
  _GEO["loaded"] = True
  try:
    import struct
    cc = json.loads((CC_DIR / "geoip" / "countries.json").read_text())
    _GEO["cc"] = {i: row for i, row in enumerate(cc)}
    raw = (CC_DIR / "geoip" / "ipv4-country.bin").read_bytes()
    rec = struct.Struct(">IIH")
    starts, recs = [], []
    for off in range(0, len(raw) - rec.size + 1, rec.size):
      s, e, ci = rec.unpack_from(raw, off)
      starts.append(s); recs.append((e, ci))
    _GEO["v4"] = (starts, recs)
  except Exception:
    _GEO["v4"] = None


def geo_lookup(ip):
  _load_geo()
  if not _GEO["v4"]:
    return None
  import bisect
  n = _ip4_int(ip)
  if n is None:
    return None
  starts, recs = _GEO["v4"]
  i = bisect.bisect_right(starts, n) - 1
  if i < 0:
    return None
  end, ci = recs[i]
  if n > end:
    return None
  row = _GEO["cc"].get(ci)
  if not row:
    return None
  return {"cc": row[0], "lat": row[1], "lon": row[2], "name": row[3]}


def _net16(ip):
  parts = ip.split(".")
  return ".".join(parts[:2]) + ".0.0/16" if len(parts) == 4 else ip


def cc_attacks():
  window = 6
  try:
    data = loki_range('{job="router-firewall"}', limit=1500, hours=window)
  except Exception:
    return {"present": False, "total_events": 0, "window_hours": window, "countries": [],
            "top_sources": [], "geo": bool(_GEO.get("v4"))}
  by_src = {}
  prefixes = {}
  total = 0
  dest_ip = PUBLIC_IP
  for stream in data.get("data", {}).get("result", []):
    for _, line in stream.get("values", []):
      m = _DROP_RE.search(line)
      if not m:
        continue
      src, dst = m.group(1), m.group(2)
      # external source only (ignore RFC1918 / loopback / link-local / CGNAT noise)
      if _is_private(src):
        continue
      total += 1
      dest_ip = dest_ip or dst
      by_src[src] = by_src.get(src, 0) + 1
      pm = _PREFIX_RE.search(line)
      if pm:
        prefixes[pm.group(1)] = prefixes.get(pm.group(1), 0) + 1
  countries = {}
  for src, count in by_src.items():
    g = geo_lookup(src)
    key = g["cc"] if g else "??"
    c = countries.setdefault(key, {"cc": key, "name": (g["name"] if g else "Unknown"),
                                    "lat": (g["lat"] if g else 0), "lon": (g["lon"] if g else 0),
                                    "count": 0, "sources": 0})
    c["count"] += count
    c["sources"] += 1
  top_sources = sorted(({"ip": k, "net": _net16(k), "count": v, "geo": geo_lookup(k)}
                        for k, v in by_src.items()), key=lambda x: -x["count"])[:12]
  return {
    "present": True,
    "ts": datetime.now(timezone.utc).isoformat(),
    "total_events": total,
    "window_hours": window,
    "public_ip": dest_ip,
    "geo": bool(_GEO.get("v4")),
    "unique_sources": len(by_src),
    "countries": sorted(countries.values(), key=lambda x: -x["count"])[:60],
    "top_sources": top_sources,
    "top_prefixes": sorted(({"rule": k, "count": v} for k, v in prefixes.items()),
                           key=lambda x: -x["count"])[:8],
  }


class H(BaseHTTPRequestHandler):
  def send_bytes(self, status, body, content_type="application/octet-stream", extra_headers=None):
    self.send_response(status)
    self.send_header("Content-Type", content_type)
    self.send_header("Content-Length", str(len(body)))
    self.send_header("X-Content-Type-Options", "nosniff")
    self.send_header("Referrer-Policy", "same-origin")
    if extra_headers:
      for k,v in extra_headers.items():
        self.send_header(k,v)
    self.end_headers()
    self.wfile.write(body)

  def serve_guide(self, path):
    if path == "/guide":
      self.send_response(308)
      self.send_header("Location", "/guide/")
      self.end_headers()
      return

    rel = path[len("/guide/"):] if path.startswith("/guide/") else ""
    if not rel:
      rel = "index.html"

    candidate = (GUIDE_ROOT / rel).resolve()
    try:
      candidate.relative_to(GUIDE_ROOT)
    except ValueError:
      self.send_bytes(403, b"forbidden\n", "text/plain; charset=utf-8")
      return

    if candidate.is_dir():
      candidate = candidate / "index.html"
    if not candidate.is_file():
      self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")
      return

    ctype = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
    headers = {"Cache-Control":"no-cache"} if candidate.name == "index.html" else {"Cache-Control":"public, max-age=3600"}
    self.send_bytes(200, candidate.read_bytes(), ctype, headers)

  def serve_worker_media(self, path):
    # Re-encoded images and copied GLB models that the host collector placed under worker-status/media/<job>/<file>. Read-only, name-validated, size-capped.
    rel = path[len("/cc/workers/media/"):]
    root = (Path(CC_WORKER_FILE).parent / "media").resolve()
    ctype = CC_MEDIA_TYPES.get(Path(rel).suffix.lower())
    if not CC_MEDIA_NAME.match(rel) or ".." in rel or ctype is None:
      self.send_bytes(403, b"forbidden\n", "text/plain; charset=utf-8")
      return
    candidate = (root / rel).resolve()
    try:
      candidate.relative_to(root)
    except ValueError:
      self.send_bytes(403, b"forbidden\n", "text/plain; charset=utf-8")
      return
    if not candidate.is_file() or candidate.is_symlink():
      self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")
      return
    if candidate.stat().st_size > CC_MEDIA_MAX:
      self.send_bytes(413, b"too large\n", "text/plain; charset=utf-8")
      return
    self.send_bytes(200, candidate.read_bytes(), ctype, {"Cache-Control": "public, max-age=300", "X-Content-Type-Options": "nosniff"})

  def serve_cc(self, path):
    if path == "/command-center":
      self.send_response(308)
      self.send_header("Location", "/command-center/")
      self.end_headers()
      return
    rel = path[len("/command-center/"):] if path.startswith("/command-center/") else ""
    if not rel:
      rel = "index.html"
    candidate = (CC_DIR / rel).resolve()
    try:
      candidate.relative_to(CC_DIR)
    except ValueError:
      self.send_bytes(403, b"forbidden\n", "text/plain; charset=utf-8")
      return
    if candidate.is_dir():
      candidate = candidate / "index.html"
    if not candidate.is_file():
      self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")
      return
    ctype = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
    headers = {"Cache-Control": "no-cache"} if candidate.suffix in (".html", ".js", ".css") else {"Cache-Control": "public, max-age=3600"}
    self.send_bytes(200, candidate.read_bytes(), ctype, headers)

  def guide_status(self):
    s = cached("guide-status-stats", 30, stats)
    c = cached("guide-status-cluster", 30, cluster_detail)
    summary = s.get("summary", {}) if isinstance(s, dict) else {}
    cluster = s.get("cluster", {}) if isinstance(s, dict) else {}
    return {
      "generated_at": datetime.now(timezone.utc).isoformat(),
      "apps": {
        "ok": summary.get("apps_ok", 0),
        "total": summary.get("apps_total", 0),
        "errors": summary.get("apps_error", 0)
      },
      "cluster": {
        "pods_running": cluster.get("pods_running", 0),
        "pods_pending": cluster.get("pods_pending", 0),
        "pods_failed": cluster.get("pods_failed", 0),
        "deployments_unavailable": cluster.get("deployments_unavailable", 0),
        "memory_used_pct": cluster.get("memory_used_pct", 0),
        "disk_used_pct": cluster.get("disk_used_pct", 0),
        "prometheus": cluster.get("prometheus", "unknown"),
        "node_exporter": cluster.get("node_exporter", "unknown")
      },
      "problem_namespaces": (c.get("problem_namespaces", []) if isinstance(c, dict) else [])[:8]
    }

  def send(self, obj, status=200):
    b=json.dumps(obj).encode()
    self.send_response(status)
    self.send_header("Content-Type","application/json")
    self.send_header("Content-Length",str(len(b)))
    self.end_headers()
    self.wfile.write(b)

  def do_HEAD(self):
    try:
      p=self.path.split("?")[0]

      if p=="/guide":
        self.send_response(308)
        self.send_header("Location", "/guide/")
        self.end_headers()
        return

      if p.startswith("/guide/"):
        rel=p[len("/guide/"):] or "index.html"
        candidate=(GUIDE_ROOT / rel).resolve()

        try:
          candidate.relative_to(GUIDE_ROOT)
        except ValueError:
          self.send_response(403)
          self.end_headers()
          return

        if candidate.is_dir():
          candidate=candidate / "index.html"

        if not candidate.is_file():
          self.send_response(404)
          self.end_headers()
          return

        ctype=mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(candidate.stat().st_size))
        self.end_headers()
        return

      if p=="/guide-api/status":
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        return

      self.send_response(404)
      self.end_headers()

    except Exception:
      self.send_response(500)
      self.end_headers()

  def do_POST(self):
    try:
      p = self.path.split("?")[0]
      if p not in ("/cc/change-requests/decision", "/cc/break-glass"):
        self.send({"error": "not found"}, 404)
        return
      host = (self.headers.get("Host") or "").lower()
      origin = urllib.parse.urlparse(self.headers.get("Origin") or "").netloc.lower()
      if not origin or origin != host:
        self.send({"error": "cross-origin request refused"}, 403)
        return
      if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
        self.send({"error": "Content-Type must be application/json"}, 415)
        return
      length = int(self.headers.get("Content-Length") or 0)
      if not 0 < length <= 4096:
        self.send({"error": "bad body size"}, 413)
        return
      try:
        body = json.loads(self.rfile.read(length))
      except ValueError:
        self.send({"error": "invalid JSON"}, 400)
        return
      client = self.headers.get("X-Forwarded-For") or self.client_address[0]
      status, message = (bg_request if p == "/cc/break-glass" else cr_decide)(body, client)
      self.send({"ok": status == 202, "message": message}, status)
    except Exception:
      self.send({"error": "internal"}, 500)

  def do_GET(self):
    try:
      p=self.path.split("?")[0]

      if p=="/guide" or p.startswith("/guide/"):
        self.serve_guide(p)
      elif p=="/command-center" or p.startswith("/command-center/"):
        self.serve_cc(p)
      elif p=="/cc/metrics":
        self.send(cached("cc-metrics", 15, cc_metrics))
      elif p=="/cc/topology":
        self.send(cached("cc-topology", 20, cc_topology))
      elif p=="/cc/attacks":
        self.send(cached("cc-attacks", 60, cc_attacks))
      elif p=="/cc/workers":
        self.send(cached("cc-workers", 8, cc_workers))
      elif p=="/cc/change-requests":
        self.send(cc_change_requests())
      elif p=="/cc/break-glass":
        self.send(cc_break_glass())
      elif p=="/cc/llm-performance":
        self.send(cached("cc-llm-performance", 10, cc_llm_performance))
      elif p.startswith("/cc/workers/media/"):
        self.serve_worker_media(p)
      elif p=="/guide-api/status":
        self.send(self.guide_status())
      elif p=="/stats":
        self.send(stats())
      elif p=="/k3s-metrics":
        self.send(cached("k3s-metrics", 30, k3s_metrics))
      elif p=="/cluster-detail":
        self.send(cached("cluster-detail", 30, cluster_detail))
      elif p=="/llm-summary":
        self.send(cached("llm-summary", 30, llm_summary))
      elif p=="/health":
        self.send({"ok":True})
      else:
        self.send({"error":"not found","path":p}, 404)

    except Exception as e:
      self.send({"error":str(e)}, 500)

  def log_message(self, *args):
    pass

ThreadingHTTPServer(("0.0.0.0", 9000), H).serve_forever()
