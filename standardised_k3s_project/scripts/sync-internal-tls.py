#!/usr/bin/env python3
"""Propagate the cert-manager Let's Encrypt wildcard to every place that serves it (T-0116).

cert-manager renews the certificate in cert-manager/<source secret> about every 60 days. Traefik routes read a
`watoom-tls` copy in their own namespace, and homelab_rebuild's local_tls role treats the host files in
/data/watoom-local-tls as the canonical material. This copies a renewed certificate into both, so a renewal never
leaves services on an expiring copy. Run daily by watoom-internal-tls-sync.timer (installed by local_tls).

Only namespaces that already hold the target secret are updated; nothing new is created. Before the migration
(no source secret yet) it reports NO_SOURCE and changes nothing. Key material only travels over stdin, never argv.
Prints UNCHANGED or CHANGED <n>; exits non-zero if the source certificate fails validation.
"""
import argparse
import base64
import datetime
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def kubectl(*args, stdin=None):
    return subprocess.run(["kubectl", *args], input=stdin, capture_output=True, check=True).stdout


def openssl(*args, stdin):
    return subprocess.run(["openssl", *args], input=stdin, capture_output=True, check=True).stdout


def validate(cert, key, domain):
    """Fail closed: parseable, key matches, covers the wildcard, and not expiring within a week."""
    cert_pub = openssl("x509", "-pubkey", "-noout", stdin=cert)
    key_pub = openssl("pkey", "-pubout", stdin=key)
    if openssl("pkey", "-pubin", "-outform", "DER", stdin=cert_pub) != openssl("pkey", "-pubin", "-outform", "DER", stdin=key_pub):
        raise SystemExit("FAIL: certificate and private key do not match")
    sans = openssl("x509", "-noout", "-ext", "subjectAltName", stdin=cert).decode()
    if f"DNS:*.{domain}" not in sans:
        raise SystemExit(f"FAIL: certificate does not cover *.{domain}: {sans.strip()}")
    try:
        openssl("x509", "-noout", "-checkend", str(7 * 86400), stdin=cert)
    except subprocess.CalledProcessError:
        raise SystemExit("FAIL: certificate expires within 7 days; cert-manager renewal is not working")


def write_atomic(path, data, mode):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    temporary.chmod(mode)
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-namespace", default="cert-manager")
    parser.add_argument("--source-secret", default="watoom-internal-wildcard-prod-tls")
    parser.add_argument("--domain", default="internal.homelab.example")
    parser.add_argument("--canonical-dir", default="/data/watoom-local-tls")
    parser.add_argument("--target-secret", action="append", default=None,
                        help="target secret name (repeatable; default watoom-tls and watoom-code-lan-tls)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    targets = args.target_secret or ["watoom-tls", "watoom-code-lan-tls"]

    try:
        source = json.loads(kubectl("-n", args.source_namespace, "get", "secret", args.source_secret, "-o", "json"))
    except subprocess.CalledProcessError:
        print("NO_SOURCE: no issued certificate yet; nothing changed")
        return
    cert = base64.b64decode(source["data"]["tls.crt"])
    key = base64.b64decode(source["data"]["tls.key"])
    validate(cert, key, args.domain)
    encoded = {"tls.crt": source["data"]["tls.crt"], "tls.key": source["data"]["tls.key"]}

    changed = []
    canonical = Path(args.canonical_dir)
    for name, data, mode in (("tls.crt", cert, 0o644), ("tls.key", key, 0o600)):
        path = canonical / name
        if not path.exists() or path.read_bytes() != data:
            changed.append(str(path))
            if not args.dry_run:
                write_atomic(path, data, mode)

    secrets = json.loads(kubectl("get", "secret", "-A", "-o", "json"))["items"]
    for item in secrets:
        meta = item["metadata"]
        if meta["name"] not in targets or meta["namespace"] == args.source_namespace:
            continue
        current = item.get("data") or {}
        if current.get("tls.crt") == encoded["tls.crt"] and current.get("tls.key") == encoded["tls.key"]:
            continue
        changed.append(f"{meta['namespace']}/{meta['name']}")
        if not args.dry_run:
            manifest = {"apiVersion": "v1", "kind": "Secret", "type": "kubernetes.io/tls",
                        "metadata": {"name": meta["name"], "namespace": meta["namespace"]}, "data": encoded}
            kubectl("apply", "-f", "-", stdin=json.dumps(manifest).encode())

    expiry = openssl("x509", "-noout", "-enddate", stdin=cert).decode().strip()
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    if changed:
        print(f"{stamp} {'WOULD_CHANGE' if args.dry_run else 'CHANGED'} {len(changed)} ({expiry}): {', '.join(changed)}")
    else:
        print(f"{stamp} UNCHANGED ({expiry})")


if __name__ == "__main__":
    sys.exit(main())
