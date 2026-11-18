#!/usr/bin/env python3
"""Off-host copy of verified WatooM-Code backups, pulled by the rig.

The rig has no listening services, so it pulls over a jailed SFTP account that can
read only the export tree and write only receipts. `export` publishes the newest
verified runs (checked against their manifest) to the export tree, readable by the
pull group. `receipts` checks each rig receipt against the run's manifest and writes
the node-exporter metric for the newest run the rig has verified.
"""
import argparse, grp, json, os, pathlib, re, shutil, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from backup import STAMP, sha256

def verified_runs(dest):
    """Runs whose files all match their manifest, oldest first."""
    runs = []
    for run in sorted(d for d in dest.iterdir() if d.is_dir() and STAMP.match(d.name) and (d / "manifest.json").is_file()):
        files = json.loads((run / "manifest.json").read_text())["files"]
        if files and all((run / name).is_file() and sha256(run / name) == digest for name, digest in files.items()):
            runs.append(run)
    return runs

def export(dest, target, keep, gid):
    """Publish the newest `keep` verified runs to `target`; remove older exports."""
    target.mkdir(mode=0o750, parents=True, exist_ok=True)
    os.chown(target, 0, gid); target.chmod(0o750)
    wanted = verified_runs(dest)[-keep:]
    for run in wanted:
        final = target / run.name
        if final.exists():
            continue
        tmp = target / (".partial-" + run.name)
        shutil.rmtree(tmp, ignore_errors=True)
        files = json.loads((run / "manifest.json").read_text())["files"]
        for name in [*files, "manifest.json"]:
            out = tmp / name
            out.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
            shutil.copyfile(run / name, out)
        for path in [tmp, *tmp.rglob("*")]:
            os.chown(path, 0, gid); path.chmod(0o750 if path.is_dir() else 0o640)
        if any(sha256(tmp / name) != digest for name, digest in files.items()):
            raise RuntimeError("export copy mismatch: " + run.name)
        tmp.rename(final)
    names = {run.name for run in wanted}
    for old in target.iterdir():
        if old.name not in names:
            shutil.rmtree(old) if old.is_dir() else old.unlink()
    return sorted(names)

def check_receipts(target, receipts):
    """Newest run whose rig receipt matches its manifest exactly; None if none does."""
    best = None
    for receipt in receipts.glob("*.json"):
        try:
            if receipt.stat().st_size > 1 << 20:
                continue
            data = json.loads(receipt.read_text(encoding="utf-8-sig"))  # Windows PowerShell writes a BOM
            run = target / data["run"]
            if not STAMP.match(data["run"]) or not (run / "manifest.json").is_file():
                continue
            if data["files"] == json.loads((run / "manifest.json").read_text())["files"] and (best is None or data["run"] > best):
                best = data["run"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return best

def write_metric(directory, run):
    """Timestamp of the newest run verified on the rig (from its stamp)."""
    import datetime
    value = 0 if run is None else datetime.datetime.strptime(run, "%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()
    tmp = directory / ".watoom_backup_offhost.prom.tmp"
    tmp.write_text("# HELP watoom_backup_offhost_verified_run_timestamp_seconds Creation time of the newest backup run verified off-host.\n"
                   "# TYPE watoom_backup_offhost_verified_run_timestamp_seconds gauge\n"
                   'watoom_backup_offhost_verified_run_timestamp_seconds{target="watoom-code",host="rig"} %d\n' % value)
    tmp.chmod(0o644); tmp.rename(directory / "watoom_backup_offhost.prom")

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=["export", "receipts"])
    p.add_argument("--dest", type=pathlib.Path, default=pathlib.Path("/data/backups/watoom-code"))
    p.add_argument("--export", type=pathlib.Path, default=pathlib.Path("/data/backups/offhost/export"))
    p.add_argument("--receipts", type=pathlib.Path, default=pathlib.Path("/data/backups/offhost/receipts"))
    p.add_argument("--keep", type=int, default=3)
    p.add_argument("--group", default="watoom-backup-pull")
    p.add_argument("--textfile-dir", type=pathlib.Path, default=pathlib.Path("/var/lib/node_exporter/textfile"))
    a = p.parse_args()
    if a.action == "export":
        print(json.dumps({"exported": export(a.dest, a.export, a.keep, grp.getgrnam(a.group).gr_gid)}))
    else:
        run = check_receipts(a.export, a.receipts)
        write_metric(a.textfile_dir, run)
        print(json.dumps({"verified_offhost": run}))

if __name__ == "__main__":
    main()
