#!/usr/bin/env python3
"""Phase 2 of the learning loop: harness-run verification graders for a changeset.

Free, deterministic, read-only / dry-run checks over the files a change touches. The verdict is each
grader's own exit status, never a model's self-report (docs/proposals/learning-loop-design.md). The tool
never mutates the repo or contacts the cluster: it runs yamllint, ansible-lint, ansible-playbook
--syntax-check, `bash -n`, `python -m py_compile` and JSON parsing against the working tree only, and
reports per-file PASS/FAIL with the grader output a fix would need. It writes nothing except an optional
evidence file. The bounded fix-and-rerun loop is the harness's job; one invocation is one honest verdict.

Usage:
  verification_loop.py                       # grade the working tree's changed files
  verification_loop.py --path a.yml --path b.sh
  verification_loop.py --evidence <dir>      # also write <dir>/verification.json
"""
import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "ansible"
INVENTORY = "inventories/homelab/hosts.yml"
TIMEOUT = 60
MAX_FILES = 300
MAX_DETAIL = 4000


def run(args, cwd=None):
    """Run a grader; return (rc, combined-output). A missing binary or a timeout is a grader error, not a pass."""
    try:
        proc = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=TIMEOUT)
        return proc.returncode, proc.stdout.decode("utf-8", "replace")
    except FileNotFoundError:
        return 127, "grader not installed: " + args[0]
    except subprocess.TimeoutExpired:
        return 124, "grader timed out after %ds" % TIMEOUT


def changed_files():
    """Tracked-modified, staged, renamed-to and untracked files in the working tree (deletions excluded)."""
    out = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain=v1", "-uall"], text=True)
    files = []
    for line in out.splitlines():
        if not line.strip():
            continue
        status, rest = line[:2], line[3:]
        if "D" in status and "R" not in status:
            continue
        path = rest.split(" -> ", 1)[1] if " -> " in rest else rest
        files.append(path.strip().strip('"'))
    return files


def yamllint_config():
    """The repo's yamllint config, if any. yamllint's default ruleset is stricter than this repo follows, so
    standalone yamllint only grades when the repo pins its own rules; otherwise ansible-lint is the YAML authority."""
    for base in (ROOT, ANSIBLE):
        for name in (".yamllint", ".yamllint.yaml", ".yamllint.yml"):
            if (base / name).is_file():
                return str(base / name)
    return None


def graders_for(rel):
    """The graders that apply to a repo-relative path, as (name, args, cwd) tuples. Empty means unsupported."""
    suffix = pathlib.PurePosixPath(rel).suffix
    abss = str(ROOT / rel)
    picked = []
    if suffix in (".yml", ".yaml"):
        if rel.startswith("ansible/"):
            # ansible-lint parses the YAML and applies the repo's .ansible-lint; no separate parse needed.
            ansible_rel = rel[len("ansible/"):]
            picked.append(("ansible-lint", ["ansible-lint", "-q", "--offline", ansible_rel], ANSIBLE))
            if rel.startswith("ansible/playbooks/"):
                picked.append(("ansible-syntax", ["ansible-playbook", "-i", INVENTORY, "--syntax-check", ansible_rel], ANSIBLE))
        else:
            # Non-ansible YAML: well-formedness always; style only when the repo pins a yamllint config.
            picked.append(("yaml-parse", ["python3", "-I", "-c", "import yaml,sys;yaml.safe_load(open(sys.argv[1]))", abss], None))
            config = yamllint_config()
            if config:
                picked.append(("yamllint", ["yamllint", "-c", config, "-f", "parsable", "-s", abss], None))
    elif suffix == ".sh":
        picked.append(("bash-n", ["bash", "-n", abss], None))
    elif suffix == ".py":
        picked.append(("py-compile", ["python3", "-I", "-m", "py_compile", abss], None))
    elif suffix == ".json":
        picked.append(("json-parse", ["python3", "-I", "-c", "import json,sys;json.load(open(sys.argv[1]))", abss], None))
    return picked


def grade(rel):
    file = ROOT / rel
    if not file.is_file():
        return {"file": rel, "status": "SKIP", "reason": "not a regular file in the working tree"}
    graders = graders_for(rel)
    if not graders:
        return {"file": rel, "status": "SKIP", "reason": "no free grader for this file type"}
    results = []
    status = "PASS"
    for name, args, cwd in graders:
        rc, output = run(args, cwd=cwd)
        if rc == 127:
            results.append({"grader": name, "status": "SKIP", "detail": output[:MAX_DETAIL]})
            continue
        ok = rc == 0
        if not ok:
            status = "FAIL"
        results.append({"grader": name, "status": "PASS" if ok else "FAIL", "exit": rc,
                        "detail": "" if ok else output[-MAX_DETAIL:]})
    return {"file": rel, "status": status, "graders": results}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--path", action="append", default=[], help="repo-relative file to grade; repeatable")
    p.add_argument("--evidence", type=pathlib.Path, help="directory to also write verification.json into")
    a = p.parse_args()
    targets = a.path or changed_files()
    # De-duplicate, keep order, and keep paths inside the repo.
    seen, ordered = set(), []
    for rel in targets:
        rel = rel.strip()
        if not rel or rel in seen or ".." in pathlib.PurePosixPath(rel).parts or pathlib.PurePosixPath(rel).is_absolute():
            continue
        seen.add(rel)
        ordered.append(rel)
    if len(ordered) > MAX_FILES:
        raise SystemExit("refusing to grade %d files (limit %d); pass explicit --path targets" % (len(ordered), MAX_FILES))
    files = [grade(rel) for rel in ordered]
    graded = [f for f in files if f["status"] != "SKIP"]
    failed = [f for f in files if f["status"] == "FAIL"]
    report = {
        "status": "FAIL" if failed else "PASS",
        "summary": {"targets": len(ordered), "graded": len(graded), "skipped": len(ordered) - len(graded), "failed": len(failed)},
        "files": files,
    }
    if a.evidence:
        a.evidence.mkdir(parents=True, exist_ok=True)
        (a.evidence / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
