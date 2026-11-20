#!/usr/bin/python3 -I
"""Operator-only fast-forward refresh; preserve model dev history and tool enablement."""

import argparse, fcntl, json, os, pathlib, pwd, re, subprocess, time

SOURCE = pathlib.Path("/data/github/watoom-standardised-homelab")
WORK = pathlib.Path("/data/github/watoom-homelab-dev")
BARE = pathlib.Path("/data/ai/git/watoom-homelab-dev.git")
HOME = pathlib.Path("/data/ai/helper-scripts/dev-workspace")


def git(root, *args, user=None):
    cmd = ["git", "-c", "safe.directory=" + str(SOURCE), "-c", "safe.directory=" + str(root), "-C", str(root), *args]
    if user:
        cmd = ["runuser", "-u", user, "--", *cmd]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if p.returncode:
        raise RuntimeError("Git refresh failed: " + p.stderr[-1200:])
    return p.stdout.strip()


def refresh(baseline):
    if os.geteuid() != 0:
        raise PermissionError("Operator privilege required")
    if not re.fullmatch("[a-f0-9]{40}", baseline):
        raise ValueError("Exact published baseline required")
    for ref in ["main", "dev", "origin/main", "origin/dev"]:
        if git(SOURCE, "rev-parse", ref) != baseline:
            raise RuntimeError("Main/dev published refs must agree before refresh")
    lock = (HOME / "state/serial.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        for p in (HOME / "state/tasks").glob("*/state.json"):
            if json.loads(p.read_text()).get("phase") == "RUNNING":
                raise RuntimeError("Development task active; retain it")
        if git(WORK, "status", "--porcelain"):
            raise RuntimeError("Preserve existing development changes")
        if git(WORK, "branch", "--show-current") != "dev":
            raise RuntimeError("Canonical model checkout is not on dev")
        before = git(WORK, "rev-parse", "HEAD")
        git(SOURCE, "merge-base", "--is-ancestor", before, baseline)
        old = git(BARE, "rev-parse", "refs/heads/dev")
        git(SOURCE, "merge-base", "--is-ancestor", old, baseline)
        server = pwd.getpwuid((BARE / "objects").stat().st_uid).pw_name
        runner = pwd.getpwuid(WORK.stat().st_uid).pw_name
        # Bare HEAD/config are intentionally operator-owned; do not weaken that boundary.
        if old != baseline:
            git(BARE, "fetch", "--no-tags", "--no-write-fetch-head", str(SOURCE), "refs/heads/main:refs/heads/dev")
        git(WORK, "fetch", "--no-tags", str(SOURCE), "refs/heads/main:refs/remotes/origin/dev", user=runner)
        git(WORK, "merge", "--ff-only", "refs/remotes/origin/dev", user=runner)
        assert git(BARE, "rev-parse", "refs/heads/dev") == git(WORK, "rev-parse", "HEAD") == baseline
        assert not git(WORK, "status", "--porcelain")
        p = HOME / "config.json"
        config = json.loads(p.read_text())
        config["baseline"] = baseline
        tmp = p.with_suffix(".refresh.tmp")
        tmp.write_text(json.dumps(config, indent=2) + "\n")
        os.chmod(tmp, p.stat().st_mode & 0o777)
        os.chown(tmp, p.stat().st_uid, p.stat().st_gid)
        os.replace(tmp, p)
        receipt = {
            "status": "PASS",
            "before": before,
            "baseline": baseline,
            "refreshed_at": time.time(),
            "enabled_unchanged": config["enabled"],
            "workspace": str(WORK),
            "bare": str(BARE),
        }
        (HOME / "last-refresh.json").write_text(json.dumps(receipt, indent=2) + "\n")
        return receipt
    finally:
        lock.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("baseline")
    print(json.dumps(refresh(p.parse_args().baseline)))
