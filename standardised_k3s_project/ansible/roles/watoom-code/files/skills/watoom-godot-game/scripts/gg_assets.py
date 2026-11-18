#!/usr/bin/env python3
"""Pick an owned model, bring it into the project, and check it, without reading the 970-line asset-index.md.

  gg_assets.py find  --query "dragon skeleton" [--ext glb] [--animated] [--max-mb 30] [--max 8]     compact ranked list from the model index
  gg_assets.py use   --asset ID --project P --slot hero [--allow-large] [--replace]                 copy it to assets/library/<slot>.<ext> and record it in assets/library/ASSETS.md
  gg_assets.py check --project P --slot hero                                                         engine inspection: size, triangles, skeleton, materials, with the same verdicts as gg_catalog

The index (`tools/fab/build_model_index.py`, default /data/ai/assets/catalog/model-index.json) lists every .glb/.gltf/.fbx in the owned packs and the loose files in
humble_assets, with what each .glb really holds (meshes, skins, animation names). `find` and `use` read the library, so run them in your session (not in the worker
container, which has no library mount); `check` runs in the worker. Only files named in the index are copied, nothing is downloaded or converted: for an Unreal-only pack
use the `watoom-fab-owned-assets` conversion route first. Prefer .glb (textures inside) over .fbx (textures are NOT copied and may render white). A file over --max-mb
(30) is refused unless --allow-large: every worker job syncs the whole project to the Bazzite worker, so keep big files out of scratch copies.
Exit codes: 0 ok | 1 check failed | 2 refused.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gg_catalog  # noqa: E402
import gg_godot  # noqa: E402

INDEX = os.environ.get("GG_MODEL_INDEX", "/data/ai/assets/catalog/model-index.json")
ROOTS = ("/data/ai/assets/fab", "/data/ai/assets/humble_assets")
SLOT_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
DEFAULT_MAX_MB = 30.0
CHECK_CATEGORY = "prop"       # 0.3..30 m: a character, creature or weapon seen in a UI model view


def load_index(path=None):
    path = path or INDEX
    if not os.path.isfile(path):
        raise gg_godot.Refused("model index %s not found: run `tools/fab/build_model_index.py` (operator) or call this from your own session; the worker container has no asset library" % path)
    with open(path) as f:
        doc = json.load(f)
    if doc.get("schema") != 1:
        raise gg_godot.Refused("model index %s has schema %r, expected 1" % (path, doc.get("schema")))
    return doc["models"]


def score(entry, tokens):
    hay, base = (entry["pack"] + " " + entry["id"]).lower(), entry["id"].lower()
    s = 0
    for t in tokens:
        if t in base:
            s += 2
        elif t in hay:
            s += 1
    return s


def find(models, query, ext=None, animated=False, max_mb=DEFAULT_MAX_MB, limit=8):
    """Ranked entries matching every query token somewhere in pack/id; skeleton-less FBX animation clips are not hidden but rank last."""
    tokens = [t for t in re.split(r"[^a-z0-9]+", query.lower()) if t]
    out = []
    for m in models:
        if ext and m["ext"] != ext:
            continue
        if max_mb is not None and m["bytes"] > max_mb * 1024 * 1024:
            continue
        g = m.get("glb") or {}
        if animated and not g.get("animations"):
            continue
        if tokens and not all(t in (m["pack"] + " " + m["id"]).lower() for t in tokens):
            continue
        out.append((score(m, tokens), m["ext"] == "glb", bool(m.get("converted")), -m["bytes"], m))
    out.sort(key=lambda r: r[:4], reverse=True)
    return [r[4] for r in out[:limit]], len(out)


def describe(m):
    g = m.get("glb")
    facts = ("meshes %d skins %d anims %d%s" % (g["meshes"], g["skins"], g["animations"], " (" + ", ".join(g["animation_names"][:3]) + ")" if g["animation_names"] else "")) if g else "no facts (fbx: textures not inside)"
    return "%s  %s  %.1f MB  %s" % (m["id"], m["ext"], m["bytes"] / 1048576.0, facts)


def safe_source(entry):
    p = os.path.realpath(entry["path"])
    if not any(p == r or p.startswith(r + os.sep) for r in ROOTS) or os.path.islink(entry["path"]) or not os.path.isfile(p):
        raise gg_godot.Refused("source %s is not a regular file under %s" % (entry["path"], " or ".join(ROOTS)))
    return p


def use(models, asset, project, slot, allow_large=False, replace=False, max_mb=DEFAULT_MAX_MB):
    project = os.path.abspath(project)
    if not SLOT_RE.match(slot):
        raise gg_godot.Refused("slot must be lowercase letters, digits or _, starting with a letter (max 32), got %r" % slot)
    if not os.path.isdir(project):
        raise gg_godot.Refused("%s is not a directory" % project)
    entry = next((m for m in models if m["id"] == asset), None)
    if not entry:
        close = [m["id"] for m in models if asset.lower()[:12] in m["id"].lower()][:5]
        raise gg_godot.Refused("no asset %r in the model index%s" % (asset, "; similar: " + ", ".join(close) if close else ""))
    src = safe_source(entry)
    if entry["bytes"] > max_mb * 1024 * 1024 and not allow_large:
        raise gg_godot.Refused("%s is %.0f MB (limit %.0f): every worker job syncs the whole project; pick a smaller model or pass --allow-large and keep it out of scratch copies" % (asset, entry["bytes"] / 1048576.0, max_mb))
    lib = os.path.join(project, "assets", "library")
    dest = os.path.join(lib, slot + "." + entry["ext"])
    existing = [f for f in (os.listdir(lib) if os.path.isdir(lib) else []) if f.rsplit(".", 1)[0] == slot and f != "ASSETS.md"]
    if existing and not replace:
        raise gg_godot.Refused("slot %s already holds %s: pass --replace to swap it" % (slot, existing[0]))
    os.makedirs(lib, exist_ok=True)
    for f in existing:
        os.remove(os.path.join(lib, f))
    shutil.copyfile(src, dest)
    with open(dest, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    notes = os.path.join(lib, "ASSETS.md")
    old = []
    if os.path.isfile(notes):
        with open(notes) as f:
            old = f.read().splitlines()
    rows = [ln for ln in old if ln.startswith("| ") and not ln.startswith("| slot") and not ln.startswith("| ---") and not ln.startswith("| %s |" % slot)]
    rows.append("| %s | %s | %s | %s | %s |" % (slot, os.path.basename(dest), entry["id"], entry["pack"], sha[:16]))
    with open(notes, "w") as f:
        f.write("# Assets used (owned library; copied, not converted)\n\n| slot | file | asset id | pack | sha256 |\n| --- | --- | --- | --- | --- |\n" + "\n".join(sorted(rows)) + "\n")
    return dest, entry, sha


def check_flags(data):
    """gg_catalog's static inspection verdicts for a prop-sized model, minus the scatter-only 'origin on the ground' rule. -> list of {level, msg}."""
    return [f for f in gg_catalog.asset_flags(data, CHECK_CATEGORY) if "scatter puts the origin" not in f["msg"]]


def check(project, slot, run=gg_godot.run):
    project = os.path.abspath(project)
    lib = os.path.join(project, "assets", "library")
    files = [f for f in (os.listdir(lib) if os.path.isdir(lib) else []) if f.rsplit(".", 1)[0] == slot and f != "ASSETS.md"]
    if not files:
        raise gg_godot.Refused("slot %s has no file in assets/library: run `gg_assets.py use` first" % slot)
    r = run(project, "inspect_asset", {"scene": "res://assets/library/" + files[0]}, render=False, timeout=300)
    data = (r.result or {}).get("data")
    if r.code != 0 or not data:
        print("gg_assets check: exit %d: %s (job %s)" % (r.code or 4, r.why, r.job_dir))
        return r.code or 4
    s = data["aabb"]["size"]
    print("  %s: size %.2f x %.2f x %.2f m, %d triangles, %d mesh(es), %d skeleton(s), %d animation player(s), %d material(s)" % (
        files[0], s[0], s[1], s[2], data["triangles"], data["meshes"], data["skeletons"], data["animation_players"], len(data["materials"])))
    flags = check_flags(data)
    for f in flags:
        print("  [%s] %s" % (f["level"].upper(), f["msg"]))
    bad = [f for f in flags if f["level"] == "error"]
    print("gg_assets check: %s (%d error(s), %d warning(s); job %s)" % ("FAIL" if bad else "PASS", len(bad), sum(f["level"] == "warn" for f in flags), r.job_dir))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("find"); p.add_argument("--query", default=""); p.add_argument("--ext", choices=["glb", "gltf", "fbx"]); p.add_argument("--animated", action="store_true")
    p.add_argument("--max-mb", type=float, default=DEFAULT_MAX_MB); p.add_argument("--max", type=int, default=8); p.add_argument("--index", default=None)
    p = sub.add_parser("use"); p.add_argument("--asset", required=True); p.add_argument("--project", required=True); p.add_argument("--slot", required=True)
    p.add_argument("--allow-large", action="store_true"); p.add_argument("--replace", action="store_true"); p.add_argument("--index", default=None)
    p = sub.add_parser("check"); p.add_argument("--project", required=True); p.add_argument("--slot", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "find":
            models = load_index(a.index)
            hits, total = find(models, a.query, a.ext, a.animated, a.max_mb, a.max)
            for m in hits:
                print(describe(m))
            print("gg_assets find: %d shown of %d match(es) in %d indexed model files%s" % (len(hits), total, len(models), "" if hits else "; widen the query or drop --animated/--ext (zip-only and Unreal-only packs are not in the index)"))
            return 0
        if a.cmd == "use":
            dest, entry, sha = use(load_index(a.index), a.asset, a.project, a.slot, a.allow_large, a.replace)
            print("gg_assets use: %s -> %s (%.1f MB, sha256 %s)%s" % (entry["id"], dest, entry["bytes"] / 1048576.0, sha[:12],
                  "\n  WARNING: fbx textures are not copied; materials may render white: prefer a .glb" if entry["ext"] == "fbx" else ""))
            return 0
        return check(a.project, a.slot)
    except gg_godot.Refused as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
