"""Append-only record of what was released: image digest, OCI source revision and IaC commit.

Git holds the reviewed pins (ansible/vars/watoom-code.yml); this host-state ledger
records each verified release so verify-iac can prove running image == reviewed commit
without release tools rewriting the checkout.
"""
import datetime, json, os, pathlib, subprocess, urllib.request

LEDGER = pathlib.Path("/data/ai/helper-scripts/state/watoom-code-release-ledger.jsonl")
REGISTRY = "http://127.0.0.1:5000"
ACCEPT = "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json"

def image_revision(image):
    """The org.opencontainers.image.revision label of a local-registry digest reference."""
    name, digest = image.split("/", 1)[1].split("@")
    req = urllib.request.Request(f"{REGISTRY}/v2/{name}/manifests/{digest}", headers={"Accept": ACCEPT})
    with urllib.request.urlopen(req, timeout=10) as r: manifest = json.load(r)
    with urllib.request.urlopen(f"{REGISTRY}/v2/{name}/blobs/{manifest['config']['digest']}", timeout=10) as r:
        return json.load(r).get("config", {}).get("Labels", {}).get("org.opencontainers.image.revision", "")

def iac_commit(root):
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True).stdout.strip())
    return head, dirty

def append(image, source_commit, iac_root, tool, evidence, ledger=LEDGER, **extra):
    head, dirty = iac_commit(iac_root)
    entry = {"time": datetime.datetime.now(datetime.timezone.utc).isoformat(), "image": image,
             "source_commit": source_commit, "iac_commit": head, "iac_dirty": dirty,
             "tool": tool, "evidence": str(evidence), **extra}
    ledger.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(ledger, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n"); f.flush(); os.fsync(f.fileno())
    return entry

def entries(ledger=LEDGER):
    if not ledger.exists(): return []
    return [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]

def latest(ledger=LEDGER):
    rows = entries(ledger)
    return rows[-1] if rows else None
