#!/usr/bin/env python3
"""Copy non-Unreal Fab downloads (FBX/GLB/OBJ) from the rig's Epic vault to the server (stdlib only).

Fab items that are not Unreal packs cannot be fetched by epic-fab (it only knows UE asset ids). The owner downloads them in the Epic launcher
(Fab library, choose the format, Download); they land on the rig in C:\\ProgramData\\Epic\\EpicGamesLauncher\\VaultCache\\FabLibrary\\<Title>-<first 8 of the listing uuid>
(the vault is a junction to F:\\UnrealData\\VaultCache). This lists and copies them over the maintenance account `migrate`
(key /data/ai/rig-migrate-ssh/key, only from the lab server, key-only; the owner enables it with setup-rig.ps1 -Admin and it expires on its own):

  rig_vault_fetch.py list [--match WORD ...]                    folders in FabLibrary (optionally only names containing a WORD)
  rig_vault_fetch.py copy ID8 [ID8 ...] [--dest DIR]            copy the folders whose name ends with -ID8 (default dest /data/ai/assets/fab-library-extras)

An item's listing uuid comes from `epic-fab search <title>`; register owned non-UE items with `epic-fab extras add <uuid> "note"` and
`tools/fab/owned_catalog.py refresh`. Read-only on the rig: nothing is changed there. After copying, import into Unreal straight from the rig path with
tools/rig-ue-mcp/ue_place_assets.py (see its docstring), or from the copied files.
"""
import argparse
import os
import subprocess
import sys

KEY = "/data/ai/rig-migrate-ssh/key"
KNOWN = "/data/ai/ue-mcp-ssh/known_hosts"
HOST = "migrate@10.99.1.44"
VAULT_WIN = r"C:\ProgramData\Epic\EpicGamesLauncher\VaultCache\FabLibrary"
VAULT_SCP = "C:/ProgramData/Epic/EpicGamesLauncher/VaultCache/FabLibrary"


def ssh_base():
    return ["-i", KEY, "-o", "UserKnownHostsFile=" + KNOWN, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]


def list_vault():
    out = subprocess.run(["ssh"] + ssh_base() + ["-p", "2224", HOST, 'dir /b "%s"' % VAULT_WIN], capture_output=True, text=True, timeout=90)
    if out.returncode:
        raise SystemExit("ssh to the rig failed (is the migrate account enabled? setup-rig.ps1 -Admin on the rig): " + out.stderr.strip()[:200])
    return [x.strip() for x in out.stdout.splitlines() if x.strip()]


def pick(names, ids):
    """Folders ending in -<id8> for each id (an id may be a full uuid; only its first 8 characters count)."""
    want = [i.replace("-", "")[:8].lower() for i in ids]
    return [n for n in names if any(n.lower().endswith("-" + w) for w in want)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--match", nargs="*", default=[])
    cp = sub.add_parser("copy")
    cp.add_argument("ids", nargs="+")
    cp.add_argument("--dest", default="/data/ai/assets/fab-library-extras")
    a = ap.parse_args(argv)
    names = list_vault()
    if a.cmd == "list":
        for n in names:
            if not a.match or any(m.lower() in n.lower() for m in a.match):
                print(n)
        return 0
    found = pick(names, a.ids)
    missing = [i for i in a.ids if not pick(names, [i])]
    os.makedirs(a.dest, exist_ok=True)
    for n in found:
        r = subprocess.run(["scp", "-r"] + ssh_base() + ["-P", "2224", "%s:%s/%s" % (HOST, VAULT_SCP, n), a.dest], timeout=1800)
        print("%s %s" % ("copied" if r.returncode == 0 else "FAILED", n))
    for m in missing:
        print("not in the vault yet:", m)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
