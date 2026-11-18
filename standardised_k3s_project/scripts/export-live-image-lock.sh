#!/usr/bin/env bash
# WatooM operator notes:
# - Purpose: Reads live workload images and exports a lock-style reference for reproducible future rebuilds.
# - Style: fail fast, print what is happening, and keep paths rooted in the repo unless the script is intentionally touching host state.
# - Safety: review kubectl, docker, hostPath, VPN, and secret-handling commands before running on a live node.
set -euo pipefail

ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OUT="${OUT:-$ROOT/docs/LIVE_IMAGE_LOCK.md}"
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
export KUBECONFIG

tmp="$(mktemp)"
docker_tmp="$(mktemp)"
kubectl get pods -A -o json > "$tmp"

if command -v docker >/dev/null 2>&1; then
  docker ps -q | while read -r id; do
    [ -n "$id" ] || continue
    docker inspect \
      --format '{{json .Name}} {{json .Config.Image}} {{json .Image}}' \
      "$id"
  done > "$docker_tmp"
fi

python3 - "$tmp" "$docker_tmp" "$OUT" <<'PY'
import json
import sys
from collections import OrderedDict

src, docker_src, out = sys.argv[1], sys.argv[2], sys.argv[3]
data = json.load(open(src))
rows = []
seen = OrderedDict()
docker_rows = []

for item in data["items"]:
    ns = item["metadata"]["namespace"]
    pod = item["metadata"]["name"]
    specs = {c["name"]: c["image"] for c in item["spec"].get("containers", [])}
    stats = {s["name"]: s.get("imageID", "") for s in item.get("status", {}).get("containerStatuses", [])}
    for name, image in specs.items():
        digest = stats.get(name, "")
        key = (ns, name, image, digest)
        if key not in seen:
            seen[key] = pod

for (ns, container, image, digest), pod in seen.items():
    rows.append((ns, pod, container, image, digest))

rows.sort()

with open(docker_src) as f:
    for line in f:
        parts = line.rstrip("\n").split(" ", 2)
        if len(parts) != 3:
            continue
        name, image, image_id = (json.loads(part) for part in parts)
        docker_rows.append((name.lstrip("/"), image, image_id))

docker_rows.sort()

with open(out, "w") as f:
    f.write("# Live Image Lock\n\n")
    f.write("Known-good images observed from the running cluster and Docker edge stacks. Use this when turning floating tags into digest pins or auditing rebuild drift.\n\n")
    f.write("## Kubernetes\n\n")
    f.write("| Namespace | Pod | Container | Manifest Image | Live Image Digest |\n")
    f.write("|---|---|---|---|---|\n")
    for row in rows:
        f.write("| " + " | ".join(x.replace("|", "\\|") for x in row) + " |\n")
    if docker_rows:
        f.write("\n## Docker\n\n")
        f.write("| Container | Compose Image | Live Image ID |\n")
        f.write("|---|---|---|\n")
        for row in docker_rows:
            f.write("| " + " | ".join(x.replace("|", "\\|") for x in row) + " |\n")
PY

rm -f "$tmp" "$docker_tmp"
echo "Wrote $OUT"
