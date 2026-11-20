#!/usr/bin/env python3
"""Publish a filtered current snapshot from fresh Git objects, without private ancestry."""

import argparse, hashlib, json, os, pathlib, subprocess


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True, type=pathlib.Path)
    ap.add_argument("--publish-main", action="store_true")
    a = ap.parse_args()
    project = pathlib.Path(__file__).resolve().parents[2]

    def run(args, cwd=project, env=None, check=True):
        p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
        if check and p.returncode:
            raise RuntimeError(p.stderr[-800:])
        return p

    repo = pathlib.Path(run(["git", "rev-parse", "--show-toplevel"]).stdout.strip())
    out = a.evidence.resolve()
    assert out.is_relative_to(pathlib.Path("/data/ai/helper-scripts/reports"))
    record = out / "prepared-publication.json"
    if not a.publish_main:
        out.mkdir(mode=0o700, exist_ok=False)
        assert not run(["git", "status", "--porcelain"]).stdout, "Commit current safe work first"
        run(["git", "fetch", "origin", "refs/heads/main:refs/remotes/origin/main"])
        base = run(["git", "rev-parse", "origin/main"]).stdout.strip()
        head = run(["git", "rev-parse", "HEAD"]).stdout.strip()
        paths = json.loads((project / "tools/git/private-publication-excludes.json").read_text())["paths"]
        assert paths and all(
            not pathlib.PurePosixPath(p).is_absolute() and ".." not in pathlib.PurePosixPath(p).parts for p in paths
        )
        forbidden = set()
        for path in paths:
            for commit in run(["git", "rev-list", "HEAD", "--", path], cwd=repo).stdout.splitlines():
                value = run(["git", "rev-parse", commit + ":" + path], check=False)
                if value.returncode == 0:
                    forbidden.add(value.stdout.strip())
        assert forbidden, "Expected private history must be identified before export"
        env = {**os.environ, "GIT_INDEX_FILE": str(out / "publication.index")}
        run(["git", "read-tree", head], env=env)
        for path in paths:
            run(["git", "update-index", "--force-remove", "--", path], env=env, cwd=repo)
        tree = run(["git", "write-tree"], env=env).stdout.strip()
        commit = run(
            [
                "git",
                "commit-tree",
                tree,
                "-p",
                base,
                "-m",
                "Publish accepted Unreal dungeon platform, safe recovery and current operations guide",
            ]
        ).stdout.strip()
        ref = "refs/heads/codex/safe-publication-" + out.name
        run(["git", "update-ref", ref, commit, "0" * 40])
        bundle = out / "public-snapshot.bundle"
        run(["git", "-c", "pack.windowMemory=64m", "-c", "pack.threads=2", "bundle", "create", str(bundle), ref])
        run(["git", "bundle", "verify", str(bundle)])
        fresh = out / "publication.git"
        run(["git", "init", "--bare", str(fresh)])
        run(["git", "fetch", str(bundle), ref + ":refs/heads/main"], cwd=fresh)
        assert run(["git", "rev-parse", "refs/heads/main"], cwd=fresh).stdout.strip() == commit
        for oid in forbidden:
            assert (
                run(["git", "cat-file", "-e", oid], cwd=fresh, check=False).returncode != 0
            ), "Private blob leaked into fresh publication object store"
        for path in paths:
            assert not run(["git", "ls-tree", "-r", commit, "--", path], cwd=fresh).stdout
        assert (
            run(["git", "merge-base", "--is-ancestor", "ee893b4", commit], cwd=repo, check=False).returncode != 0
        ), "Private commit is reachable"
        remote = run(["git", "remote", "get-url", "origin"]).stdout.strip()
        assert remote == "git@github.com:YOUR_GITHUB_USER/watoom-standardised-homelab.git"
        run(["git", "remote", "add", "origin", remote], cwd=fresh)
        result = {
            "status": "PREPARED_VERIFIED",
            "source_head": head,
            "base": base,
            "tree": tree,
            "commit": commit,
            "fresh_git": str(fresh),
            "excluded_paths": paths,
            "private_blobs_excluded": len(forbidden),
            "forbidden_blob_ids": sorted(forbidden),
            "bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
            "remote": remote,
            "pushed": False,
        }
        record.write_text(json.dumps(result, indent=2))
        print(
            "PASS fresh publication object store excludes private blobs and ancestry; ready for normal fast-forward push"
        )
        return
    result = json.loads(record.read_text())
    assert result["status"] == "PREPARED_VERIFIED" and not result["pushed"]
    fresh = pathlib.Path(result["fresh_git"])
    assert fresh.parent == out and fresh.name == "publication.git"
    assert run(["git", "rev-parse", "HEAD"]).stdout.strip() == result["source_head"]
    assert not run(["git", "status", "--porcelain"]).stdout
    remote = run(["git", "ls-remote", "origin", "refs/heads/main"], cwd=fresh).stdout.split()[0]
    assert remote == result["base"], "Remote main changed; regenerate/reconcile rather than force"
    for oid in result["forbidden_blob_ids"]:
        assert run(["git", "cat-file", "-e", oid], cwd=fresh, check=False).returncode != 0
    assert run(["git", "rev-parse", "refs/heads/main"], cwd=fresh).stdout.strip() == result["commit"]
    run(["git", "push", "origin", "refs/heads/main:refs/heads/main"], cwd=fresh)
    assert run(["git", "ls-remote", "origin", "refs/heads/main"], cwd=fresh).stdout.split()[0] == result["commit"]
    result.update(status="PUBLISHED_PASS", pushed=True)
    record.write_text(json.dumps(result, indent=2))
    # The private branch remains local. Switch the authoritative tree directly to
    # the identical public tree (only the preserved private source file disappears).
    wt = run(["git", "worktree", "list", "--porcelain"]).stdout
    if "branch refs/heads/main" not in wt:
        old = run(["git", "rev-parse", "refs/heads/main"]).stdout.strip()
        assert old == result["base"], "Local main changed; keep private checkout without resetting it"
        run(["git", "update-ref", "refs/heads/main", result["commit"], old])
        run(["git", "fetch", "origin", "refs/heads/main:refs/remotes/origin/main"])
        run(["git", "switch", "main"])
        assert not run(["git", "status", "--porcelain"]).stdout
        result["authoritative_checkout"] = "main clean"
    else:
        result["authoritative_checkout"] = "Main already checked out elsewhere; original tree preserved"
    record.write_text(json.dumps(result, indent=2))
    print("PASS normal main push verified; private history stayed local; " + result["authoritative_checkout"])


if __name__ == "__main__":
    main()
