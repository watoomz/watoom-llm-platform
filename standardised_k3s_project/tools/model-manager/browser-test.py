"""Isolated production browser acceptance; no global trust or node changes."""

import argparse, base64, json, os, subprocess
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--evidence", required=True, type=Path)
a = p.parse_args()
out = a.evidence
if (
    os.geteuid() != 0
    or not out.is_absolute()
    or out.parent != Path("/data/ai/builds")
    or not out.name.startswith("model-manager-browser-")
    or out.exists()
):
    raise SystemExit("New scoped browser evidence directory and administrative read access required")
root = Path(__file__).resolve().parent
module = root / "node_modules/playwright"
if not module.is_dir():
    raise SystemExit("Run npm ci --ignore-scripts in tools/model-manager first")
out.mkdir(mode=0o750)
os.chown(out, 1009, 1009)
home = out / "home"
db = home / ".pki/nssdb"
db.mkdir(parents=True)
for path in (home, home / ".pki", db):
    os.chown(path, 1009, 1009)
    path.chmod(0o700)
secret = json.loads(subprocess.check_output(["kubectl", "-n", "glance", "get", "secret", "watoom-tls", "-o", "json"]))
cert = out / "existing-homelab-ca.pem"
cert.write_bytes(base64.b64decode(secret["data"].get("ca.crt", secret["data"]["tls.crt"])))
cert.chmod(0o644)
prefix = ["setpriv", "--reuid=1009", "--regid=1009", "--clear-groups"]
for args in (
    ["certutil", "-N", "--empty-password", "-d", "sql:" + str(db)],
    ["certutil", "-A", "-n", "existing-homelab-test-only", "-t", "C,,", "-i", str(cert), "-d", "sql:" + str(db)],
):
    subprocess.run(prefix + args, check=True)
env = dict(
    os.environ,
    CUDA_VISIBLE_DEVICES="",
    NVIDIA_VISIBLE_DEVICES="void",
    HOME=str(home),
    BROWSER_EVIDENCE=str(out),
    PLAYWRIGHT_BROWSERS_PATH="/data/ai/toolchains/model-manager-browser",
    PLAYWRIGHT_MODULE=str(module),
)
password = Path("/data/ai/private/model-manager/password").read_text().strip()
result = subprocess.run(
    prefix + ["node", str(root / "browser-live.cjs")],
    env=env,
    input=password,
    text=True,
    capture_output=True,
    timeout=180,
)
(out / "browser.log").write_text((result.stdout + result.stderr).replace(password, "[REDACTED]"))
if result.returncode:
    raise SystemExit("Browser acceptance failed; inspect the scoped log")
print(json.dumps({"state": "PASS", "evidence": str(out / "browser.json")}))
