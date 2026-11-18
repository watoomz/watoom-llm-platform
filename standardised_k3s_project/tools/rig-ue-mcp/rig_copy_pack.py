#!/usr/bin/env python3
"""Copy downloaded Fab UE packs into the rig project's Content folder over scp (the key-only `migrate` maintenance account, created on the rig with
Add-RigMaintenanceAccount.ps1 -Admin; it has no expiry unless that was run with -Hours N, see README.md).

  rig_copy_pack.py PACKDIR [PACKDIR ...]           dry run (the default): prints the scp commands, copies nothing
  rig_copy_pack.py --apply PACKDIR [PACKDIR ...]   copy; e.g. /data/ai/assets/fab/tropical-vegetation-banana-plants-09eaba2d
  rig_copy_pack.py --plugin [--apply] PLUGINDIR --dest "<project>/Plugins/"   a code plugin (a folder with a .uplugin), e.g. the
                                                   watoom-unreal-combat skill's plugin/WatooMCombat; copied whole as <dest>/<PluginName>

--plugin (2026-11-18, T-0063): a project plugin is enabled by default and UnrealBuildTool builds it even for a Blueprint-only project, but
ONLY when the rig has a C++ toolchain (project.check_install -> toolchain.present). Without one, a plugin in Plugins/ stops the next editor
start at "missing modules", so stage it elsewhere first (e.g. <project>/Saved/Staging/) to run project.lint_cpp_header on the headers,
then copy into Plugins/ with the editor stopped and run project.build. Binaries/ and Intermediate/ are refused: build on the rig.

The copy writes straight into the live project's Content folder and overwrites files of the same name, so read the dry run first.
Before anything else (dry run included) every pack goes through ue_asset_check.py: an empty or cut-off .uasset, a name Unreal or Windows refuses,
names that differ only in case, a path too long under --dest or two packs with different bytes for one file stop it with exit 1 and nothing is
copied. Repair what can be repaired in a copy with ue_asset_fix.py; --no-asset-check copies anyway.

Each pack's `Content/<Name>` folders are merged into `<project>/Content/<Name>` (packs that share a folder, such as Megaplant_Library, merge). Afterwards the
editor needs to see the new files: `asset.list` / `asset.search` on /Game/<Name> (it scans on demand), then asset.save_all_dirty. Never run for a pack
that is not an owned, approved download.
"""
import argparse
import os
import subprocess
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", "..", "ansible", "roles", "watoom-code", "files", "skills", "watoom-texture-layering", "scripts")
sys.path.insert(0, SKILL)
sys.path.insert(0, HERE)
import ue_project  # noqa: E402
import ue_asset_check  # noqa: E402

KEY = "/data/ai/rig-migrate-ssh/key"
HOST, PORT, USER = "10.99.1.44", 2224, "migrate"
CONTENT = None  # the rig project Content folder: --dest, or rig_content_dir in the --project profile


EXTERNAL = ("__ExternalActors__", "__ExternalObjects__")


def scp_args(pack_dir, key=KEY, host=HOST, port=PORT, user=USER, dest=CONTENT):
    """One scp command per Content/<Name> folder of the pack.

    __ExternalActors__ / __ExternalObjects__ are NOT copied: they hold the World Partition actors of the pack's demo maps,
    keyed by map path, and merge into the project's own folders of the same name. The rogue pack (2026-11-19) carried 44 for
    a /Game/ThirdPerson/Maps/ThirdPersonMap it does not even ship: orphans in the project (removed by hand). A pack's demo map
    then opens without its actors; the assets themselves are complete."""
    content = os.path.join(pack_dir, "Content")
    if not os.path.isdir(content):
        raise ValueError("%s has no Content folder (not a UE pack)" % pack_dir)
    out = []
    for name in sorted(os.listdir(content)):
        src = os.path.join(content, name)
        if name in EXTERNAL:
            continue
        if os.path.isdir(src):
            out.append(["scp", "-r", "-q", "-i", key, "-P", str(port), "-o", "BatchMode=yes", src, "%s@%s:%s" % (user, host, dest)])
    return out


def plugin_scp_args(plugin_dir, key=KEY, host=HOST, port=PORT, user=USER, dest=CONTENT):
    """One scp command that copies a whole code plugin folder (it must hold exactly one .uplugin; no prebuilt binaries)."""
    plugin_dir = plugin_dir.rstrip("/")
    ups = [f for f in os.listdir(plugin_dir) if f.endswith(".uplugin")] if os.path.isdir(plugin_dir) else []
    if len(ups) != 1:
        raise ValueError("%s is not a plugin folder (needs exactly one .uplugin, found %d)" % (plugin_dir, len(ups)))
    if ups[0][:-len(".uplugin")] != os.path.basename(plugin_dir):
        raise ValueError("%s: the folder name must match %s (Unreal looks the plugin up by folder)" % (plugin_dir, ups[0]))
    for junk in ("Binaries", "Intermediate"):
        if os.path.exists(os.path.join(plugin_dir, junk)):
            raise ValueError("%s has %s/: copy the source only and build on the rig" % (plugin_dir, junk))
    if not os.path.isdir(os.path.join(plugin_dir, "Source")):
        raise ValueError("%s has no Source/ folder" % plugin_dir)
    return [["scp", "-r", "-q", "-i", key, "-P", str(port), "-o", "BatchMode=yes", plugin_dir, "%s@%s:%s" % (user, host, dest)]]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("packs", nargs="+")
    ap.add_argument("--apply", action="store_true", help="really copy (without it only the scp commands are printed)")
    ap.add_argument("--dry-run", action="store_true", help="the default; kept so older command lines still work (it wins over --apply)")
    ap.add_argument("--dest", required=True, help="rig project Content folder, e.g. F:/Documents/Unreal Projects/MyGame/Content/")
    ap.add_argument("--plugin", action="store_true", help="the folders are code plugins (copied whole into --dest, e.g. <project>/Plugins/)")
    ap.add_argument("--no-asset-check", action="store_true", help="copy even when ue_asset_check.py finds errors in a pack (default: stop, exit 1)")
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    if not a.plugin and not a.no_asset_check and ue_asset_check.gate(ue_asset_check.check_packs(a.packs, a.dest), "the pack(s)"):
        return 1
    for p in a.packs:
        for cmd in (plugin_scp_args if a.plugin else scp_args)(p.rstrip("/"), dest=a.dest):
            print(" ".join(cmd), flush=True)
            if a.dry_run or not a.apply:
                continue
            r = subprocess.run(["nice", "-n", "10"] + cmd)
            if r.returncode:
                sys.exit("scp failed (%d) for %s" % (r.returncode, cmd[-2]))
    if a.dry_run or not a.apply:
        print("dry run: nothing copied; add --apply to copy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
