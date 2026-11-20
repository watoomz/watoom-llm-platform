#!/usr/bin/env python3
"""Read-only authenticated public Skills GUI acceptance while native execution admission is fenced."""

import argparse, base64, hashlib, json, os, pathlib, subprocess
from maintenance_guard import Maintenance
import release_guard, bounded_process


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", required=True, type=pathlib.Path)
    a = p.parse_args()
    a.evidence.mkdir(parents=True, exist_ok=False)
    m = Maintenance("watoom-code", "watoom-code", a.evidence, True, True)
    release_guard.validate(m.request("/api/session/deployment-guard"), True)
    tls = m.kub("get", "secret", "watoom-code-lan-tls")["data"]
    pem = subprocess.check_output(["openssl", "x509", "-pubkey", "-noout"], input=base64.b64decode(tls["tls.crt"]))
    der = subprocess.check_output(["openssl", "pkey", "-pubin", "-outform", "DER"], input=pem)
    env = {
        **os.environ,
        "PLAYWRIGHT_MODULE": "/data/ai/projects/llm/watoom-code/native-next-review-20261014T212958Z/source/node_modules/.bun/playwright@1.59.1/node_modules/playwright",
        "CANDIDATE_PASSWORD": m.password,
        "CANDIDATE_BASE": "https://watoom-code.internal.homelab.example",
        "EVIDENCE": str(a.evidence),
        "TRUSTED_TLS_SPKI": base64.b64encode(hashlib.sha256(der).digest()).decode(),
    }
    for scheme in ["light", "dark"]:
        target = a.evidence / scheme
        target.mkdir()
        current = {
            **env,
            "EVIDENCE": str(target),
            "SKILL_COLOR_SCHEME": scheme,
            "SKILL_READABILITY_QUERY": "AgentBay Code Execution",
        }
        with (target / "runner.log").open("w") as log:
            result = bounded_process.run(
                ["node", str(pathlib.Path(__file__).with_name("skills-browser.cjs"))],
                env=current,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=75,
            )
        if result.returncode:
            raise RuntimeError("Public Skills GUI acceptance failed: " + scheme)
    release_guard.validate(m.request("/api/session/deployment-guard"), True)
    print("PASS authenticated public Skills GUI with admission fence held")


if __name__ == "__main__":
    main()
