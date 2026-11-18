#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml
from policy_engine import evaluate as evaluate_policy


def run(cmd: list[str], cwd: Path) -> dict[str, Any]:
    p = subprocess.run(cmd, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {"command": " ".join(cmd), "ok": p.returncode == 0, "exit_code": p.returncode,
            "stdout": p.stdout, "stderr": p.stderr}


def yaml_check(root: Path) -> dict[str, Any]:
    results = []
    ok = True
    for p in sorted(root.rglob("*.yml")) + sorted(root.rglob("*.yaml")):
        if any(part in {".git", ".tox", ".venv", "venv"} for part in p.parts):
            continue
        rel = str(p.relative_to(root))
        try:
            list(yaml.safe_load_all(p.read_text(encoding="utf-8")))
            results.append({"file": rel, "ok": True})
        except Exception as exc:
            ok = False
            results.append({"file": rel, "ok": False, "error": str(exc)})
    return {"ok": ok, "results": results}


def digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if not p.is_file() or ".git" in p.parts:
            continue
        h.update(str(p.relative_to(root)).encode())
        try:
            h.update(p.read_bytes())
        except OSError:
            pass
    return h.hexdigest()


def fast(root: Path) -> dict[str, Any]:
    yml = yaml_check(root)
    lint_bin = shutil.which("ansible-lint")
    if lint_bin:
        lint = run([
            lint_bin, "--profile", "production",
            "--enable-list", "no-log-password,role-argument-spec",
            "--format", "pep8", "."
        ], root)
    else:
        lint = {"ok": False, "skipped": True, "reason": "ansible-lint not installed"}
    policy = evaluate_policy(root)
    return {"ok": yml["ok"] and lint["ok"] and policy["ok"],
            "yaml": yml, "ansible_lint": lint, "policy": policy}


def ee(root: Path) -> dict[str, Any]:
    image = os.environ.get("WATOOM_ANSIBLE_EE_IMAGE")
    playbook = os.environ.get("WATOOM_ANSIBLE_EE_PLAYBOOK")
    navigator = shutil.which("ansible-navigator")
    if not image:
        return {"ok": False, "skipped": True, "reason": "WATOOM_ANSIBLE_EE_IMAGE is not configured"}
    if not navigator:
        return {"ok": False, "skipped": True, "reason": "ansible-navigator is not installed", "ee_image": image}
    if not playbook:
        return {"ok": False, "skipped": True, "reason": "WATOOM_ANSIBLE_EE_PLAYBOOK is not configured", "ee_image": image}
    pb = Path(playbook)
    if not pb.is_absolute():
        pb = root / pb
    if not pb.exists():
        return {"ok": False, "skipped": True, "reason": f"EE playbook not found: {pb}", "ee_image": image}
    syntax = run([
        navigator, "run", str(pb), "--mode", "stdout",
        "--execution-environment", "true",
        "--execution-environment-image", image,
        "--", "--syntax-check",
    ], root)
    return {"ok": syntax["ok"], "ee_image": image, "syntax": syntax}


def dynamic(root: Path) -> dict[str, Any]:
    hook = os.environ.get("WATOOM_ANSIBLE_DYNAMIC_HOOK")
    required = os.environ.get("WATOOM_ANSIBLE_DYNAMIC_REQUIRED", "false").lower() == "true"
    if not hook:
        return {"ok": not required, "skipped": True, "required": required,
                "reason": "WATOOM_ANSIBLE_DYNAMIC_HOOK is not configured"}
    result = run(["bash", "-lc", hook], root)
    result["required"] = required
    result["hook"] = hook
    return result


def state(block: dict[str, Any]) -> str:
    if block.get("skipped"):
        return "SKIPPED" if block.get("ok") else "NOT CONFIGURED"
    return "PASS" if block.get("ok") else "FAIL"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("fast", "standard", "full"))
    ap.add_argument("--root", default=".")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    result: dict[str, Any] = {"mode": args.mode, "root": str(root), "content_sha256": digest(root)}
    result["fast"] = fast(root)
    ok = result["fast"]["ok"]
    if args.mode in ("standard", "full"):
        result["ee"] = ee(root)
        ok = ok and result["ee"]["ok"]
    if args.mode == "full":
        result["dynamic"] = dynamic(root)
        ok = ok and result["dynamic"]["ok"]
    result["ok"] = ok

    print(f"{'YAML/schema':32} {state(result['fast']['yaml'])}")
    print(f"{'ansible-lint production':32} {state(result['fast']['ansible_lint'])}")
    print(f"{'WatooM semantic/security':32} {state(result['fast']['policy'])}")
    if "ee" in result:
        print(f"{'Production EE':32} {state(result['ee'])}")
    if "dynamic" in result:
        print(f"{'Dynamic/idempotence hook':32} {state(result['dynamic'])}")
    print()
    print(f"{'RESULT':32} {'PASS' if ok else 'FAIL'}")

    out = Path(args.json_out or (root / ".watoom-ansible-validation.json"))
    out.write_text(json.dumps(result, indent=2))
    print(f"\nJSON: {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
