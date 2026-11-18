#!/usr/bin/env python3
"""Repair what ue_asset_check.py marks `fixable`, in a COPY: the original is never written to (stdlib only, offline, no rig).

  ue_asset_fix.py pack PACKDIR --out NEWDIR          dry run (the default): prints the plan as JSON, writes nothing
  ue_asset_fix.py pack PACKDIR --out NEWDIR --apply  write NEWDIR (a full copy: a pack can be many GB) and NEWDIR/asset_fix_log.json
  ue_asset_fix.py sources DIR --out NEWDIR [--apply] the same for a folder of loose FBX / GLB / glTF / OBJ files
  ue_asset_fix.py manifest m.json --out new.json [--apply]   a ue_place_assets.py manifest; the log is new.json.fixlog.json

Only repairs with one possible outcome are made:
  pack      operating-system clutter (.DS_Store, Thumbs.db, desktop.ini, __MACOSX, ._*) is left out; a non-package file whose name Windows
            refuses is renamed (sanitise_name: accents dropped, anything outside A-Z a-z 0-9 _ . - becomes _).
  sources   the same clutter is left out; a mesh file (.fbx .glb .gltf .obj) with spaces or other unsafe characters is renamed.
  manifest  asset paths are put in the form /Game/Dir/Name.Name (backslashes, a leading Content/, a .uasset ending, a missing .Name);
            whitespace around a label is removed; kind is lower-cased when it is static or skeletal in another case.
Everything else is REFUSED and listed under "refused", and then nothing is written at all, with or without --apply (exit 1): a .uasset / .umap
or a folder is never renamed (the package path is stored inside the file and in every asset that references it: rename it in the editor),
a texture / .mtl / .bin is never renamed (a mesh file finds it by name), an empty or cut-off file needs a new download, names that differ
only in case, two names that would become the same name, links, duplicate labels, a zero or NaN scale and an 8-bit heightmap need a decision.
NEWDIR / new.json must not exist and must not be inside the original. After --apply the copy is checked again; exit 0 only when it passes.
The log lists every file with its sha256; ue_asset_check.py (and so the rig_copy_pack.py gate) verifies the copy against it later.
"""
import argparse
import copy
import datetime
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_asset_check as ck  # noqa: E402


def refusal(code, asset, message):
    return {"severity": "error", "code": code, "asset": asset, "message": message}


def plan_tree(src, mode, dest=None):
    """(changes, refused, warnings left) for a pack or a sources folder. A change is {action: copy | rename | drop, src, dst, reason}."""
    found = ck.check_packs([src], dest) if mode == "pack" else ck.check_sources(src)
    changes, refused = [], []
    for d, dirs, names in os.walk(src):
        rel_d = os.path.relpath(d, src).replace(os.sep, "/")
        rel_d = "" if rel_d == "." else rel_d + "/"
        for n in sorted(dirs):
            if ck.is_junk(n):
                changes.append({"action": "drop", "src": rel_d + n + "/", "dst": None, "reason": "operating-system clutter"})
            elif os.path.islink(os.path.join(d, n)):
                refused.append(refusal("link_not_copied", rel_d + n, "a link: replace it with the real folder"))
        dirs[:] = sorted(n for n in dirs if not ck.is_junk(n) and not os.path.islink(os.path.join(d, n)))
        for n in sorted(names):
            rel = rel_d + n
            if rel == ck.FIX_LOG:
                continue   # an older log describes the original, not the new copy
            if ck.is_junk(n):
                changes.append({"action": "drop", "src": rel, "dst": None, "reason": "operating-system clutter"})
            elif os.path.islink(os.path.join(d, n)):
                refused.append(refusal("link_not_copied", rel, "a link: replace it with the real file"))
            else:
                new = ck.sanitise_name(n) if ck.rename_wanted(n, mode) and ck.rename_safe(n, mode) else None
                if new and new != n:
                    changes.append({"action": "rename", "src": rel, "dst": rel_d + new, "reason": "name not safe for Windows / the import"})
                else:
                    changes.append({"action": "copy", "src": rel, "dst": rel, "reason": ""})
    taken = {}
    for c in changes:
        if c["dst"]:
            taken.setdefault(c["dst"].casefold(), []).append(c)
    for same in taken.values():
        if len(same) > 1 and any(c["action"] == "rename" for c in same):
            refused.append(refusal("rename_collision", same[0]["src"], "%s would all become %r: choose the names yourself" % (", ".join(repr(c["src"]) for c in same), same[-1]["dst"])))
    refused += [{k: f[k] for k in ("severity", "code", "asset", "message")} for f in found if f["severity"] == "error" and not f["fixable"]]
    left = [{k: f[k] for k in ("severity", "code", "asset", "message")} for f in found if f["severity"] == "warning" and not f["fixable"]]
    return changes, refused, left


def copy_hashed(src, dst):
    """Copy src to the new file dst; returns (bytes, sha256 of what was written)."""
    h, n = hashlib.sha256(), 0
    with open(src, "rb") as a, open(dst, "xb") as b:
        for block in iter(lambda: a.read(1 << 20), b""):
            b.write(block)
            h.update(block)
            n += len(block)
    shutil.copystat(src, dst)
    return n, h.hexdigest()


def out_problem(src, out):
    s, o = os.path.realpath(src), os.path.realpath(out)
    if os.path.lexists(out) or os.path.lexists(out + ".partial"):
        return "%s (or its .partial) already exists: the fixer never overwrites; choose a new --out" % out
    if o == s or o.startswith(s + os.sep) or s.startswith(o + os.sep):
        return "--out must be outside the original (%s)" % src
    return None


def apply_tree(src, out, mode, changes, log):
    tmp = out + ".partial"
    os.makedirs(tmp)
    for c in changes:
        if c["dst"]:
            dst = os.path.join(tmp, c["dst"])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            c["bytes"], c["sha256"] = copy_hashed(os.path.join(src, c["src"]), dst)
    with open(os.path.join(tmp, ck.FIX_LOG), "x") as f:
        json.dump(dict(log, changes=changes), f, indent=1)
    os.rename(tmp, out)
    return ck.check_packs([out]) if mode == "pack" else ck.check_sources(out)


def fix_manifest_items(items):
    """(a repaired deep copy, changes). Only the three deterministic repairs of the module docstring."""
    fixed, changes = copy.deepcopy(items), []
    if not isinstance(fixed, list):
        return fixed, changes

    def change(n, it, key, new, why):
        changes.append({"action": "rewrite", "item": n, "label": str(it.get("label", "")).strip(), "field": key, "before": it[key], "after": new, "reason": why})
        it[key] = new
    for n, it in enumerate(fixed):
        if not isinstance(it, dict):
            continue
        if isinstance(it.get("label"), str) and it["label"].strip() and it["label"] != it["label"].strip():
            change(n, it, "label", it["label"].strip(), "whitespace around the label")
        if isinstance(it.get("kind"), str) and it["kind"] not in ("static", "skeletal") and it["kind"].strip().lower() in ("static", "skeletal"):
            change(n, it, "kind", it["kind"].strip().lower(), "kind is matched exactly")
        norm, wrong = ck.normalise_asset_path(it.get("asset"))
        if not wrong and norm != it["asset"]:
            change(n, it, "asset", norm, "Unreal object path form /Game/Dir/Name.Name")
    return fixed, changes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=("pack", "sources", "manifest"))
    ap.add_argument("source")
    ap.add_argument("--out", required=True, help="the NEW folder (pack, sources) or file (manifest); it must not exist")
    ap.add_argument("--apply", action="store_true", help="really write --out (without it only the plan is printed)")
    ap.add_argument("--dry-run", action="store_true", help="the default; it wins over --apply")
    ap.add_argument("--dest", default=None, help="pack only: rig project Content folder, for the path length check")
    a = ap.parse_args(argv)
    src = a.source.rstrip("/") or "/"
    write = a.apply and not a.dry_run
    result = {"tool": "ue_asset_fix", "schema": 1, "kind": a.kind, "source": os.path.abspath(src), "output": os.path.abspath(a.out), "applied": False}
    fixed, left = None, []
    if a.kind == "manifest":
        found = []
        items = ck.load_json(src, src, found)
        fixed, changes = fix_manifest_items(items)
        found = found or ck.check_manifest_items(fixed, src)
        refused = [{k: f[k] for k in ("severity", "code", "asset", "message")} for f in found if f["severity"] == "error"]
        left = [{k: f[k] for k in ("severity", "code", "asset", "message")} for f in found if f["severity"] == "warning"]
    elif not os.path.isdir(src):
        changes, refused = [], [refusal("unreadable", "", "%s is not a folder" % src)]
    else:
        changes, refused, left = plan_tree(src, a.kind, a.dest)
    why = out_problem(src, a.out)
    if why:
        refused.append(refusal("bad_out", a.out, why))
    shown = [c for c in changes if c["action"] != "copy"]
    result.update(changes=shown, unchanged_files=len(changes) - len(shown), refused=refused, left_as_is=left)
    code = 1 if refused else 0
    if refused:
        result["note"] = "nothing written: %d problem(s) have no safe automatic repair" % len(refused)
    elif not write:
        result["note"] = "dry run: nothing written; add --apply to write %s" % a.out
    else:
        log = {k: result[k] for k in ("tool", "schema", "kind", "source", "output")}
        log["created"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        if a.kind == "manifest":
            with open(a.out, "x") as f:
                json.dump(fixed, f, indent=1)
            with open(a.out + ".fixlog.json", "x") as f:
                json.dump(dict(log, changes=changes, output_sha256=ck.sha256(a.out), source_sha256=ck.sha256(src)), f, indent=1)
            again = ck.check_manifest(a.out)
        else:
            again = apply_tree(src, a.out, a.kind, changes, log)
        result["applied"] = True
        result["recheck"] = ck.report(again)["summary"]
        code = 1 if result["recheck"]["error"] else 0
        result["note"] = "wrote %s; the original is untouched" % a.out + ("; the copy still FAILS the check" if code else "")
    print(json.dumps(result, indent=1))
    print("asset fix: %d change(s), %d refused. %s" % (len(shown), len(refused), result["note"]), file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
