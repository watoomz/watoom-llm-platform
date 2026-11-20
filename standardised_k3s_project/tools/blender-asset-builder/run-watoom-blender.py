#!/usr/bin/env python3
"""Production entry information, native request planning, and exact scoped rollback."""

import argparse, datetime, json, os, pathlib, subprocess, sys

REPO = pathlib.Path("/data/github/watoom-standardised-homelab/standardised_k3s_project")
RELEASE = pathlib.Path(
    "/data/ai/helper-scripts/watoom-blender-package/production-skills-20261020T093543Z/live-toolkit-release"
)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--request")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--retry-failed", action="store_true")
    p.add_argument("--engine-job")
    p.add_argument("--rollback-production", action="store_true")
    p.add_argument("--i-approve", action="store_true")
    p.add_argument("--root")
    p.add_argument("--vendor", action="store_true")
    a = p.parse_args()
    if a.rollback_production:
        if a.request or a.root or a.vendor:
            p.error("Rollback cannot be combined with asset generation or vendoring")
        evidence = pathlib.Path("/data/ai/helper-scripts/reports") / (
            "blender-production-rollback-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        )
        cmd = [
            "python3",
            str(REPO / "tools/watoom-code/deploy-platform.py"),
            "--rollback-blender-evidence",
            str(RELEASE),
            "--iac-root",
            str(REPO),
            "--evidence",
            str(evidence),
        ] + (["--i-approve"] if a.i_approve else [])
        if a.dry_run:
            print(
                json.dumps(
                    {
                        "action": "restore only recorded Toolkit image/binding/IaC pins",
                        "approval_required": True,
                        "mutations": False,
                        "command": cmd,
                    }
                )
            )
            return 0
        return subprocess.run(cmd, timeout=330).returncode
    if a.root or a.vendor:
        p.error(
            "Legacy canary execution/vendoring is diagnostic only; production uses the installed native builder. No canary is reactivated."
        )
    if a.request:
        flags = (
            ["--request", a.request]
            + (["--dry-run"] if a.dry_run else [])
            + (["--resume"] if a.resume else [])
            + (["--retry-failed"] if a.retry_failed else [])
            + (["--engine-job", a.engine_job] if a.engine_job else [])
        )
        cmd = ["python3", "/config/skills/watoom-blender-asset-builder/scripts/pipeline.py", *flags]
        if os.environ.get("OPENCODE_DB") == "/state/application.sqlite":
            return subprocess.run(cmd, timeout=1800).returncode
        if not a.dry_run:
            p.error(
                "Execute asset work through the production native builder session so admission tracks it; host --request supports --dry-run only"
            )
        return subprocess.run(
            ["kubectl", "-n", "watoom-code", "exec", "deployment/watoom-code", "-c", "app", "--", *cmd], timeout=40
        ).returncode
    print(
        json.dumps(
            {
                "production": "https://watoom-code.internal.homelab.example",
                "guide": "https://glance.internal.homelab.example/guide/#blender-production-status",
                "native_skill": "watoom-blender-asset-builder",
                "request_runner": "/config/skills/watoom-blender-asset-builder/scripts/pipeline.py --request <revision>/request.json",
                "legacy_canary": "suspended; not used",
                "rollback": "run-watoom-blender.py --rollback-production --i-approve",
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.TimeoutExpired:
        print(
            "BLOCKED: bounded operator command timed out; inspect retained evidence/admission owner before recovery",
            file=sys.stderr,
        )
        sys.exit(2)
