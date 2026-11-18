#!/usr/bin/env python3
"""Check assets before they enter the Unreal pipeline: read-only, offline, no rig and no editor (stdlib only).

  ue_asset_check.py --pack PACKDIR [--pack ...] [--dest F:/.../Content/]   what rig_copy_pack.py would copy (Content/<Name> of each pack)
  ue_asset_check.py --sources DIR [...]         loose FBX / GLB / glTF / OBJ / texture downloads (asset.import_static_mesh, import_texture)
  ue_asset_check.py --manifest m.json [--pack PACKDIR] [--size-m 4000]     a ue_place_assets.py manifest
  ue_asset_check.py --layout village.json [--pack PACKDIR] [--mesh-dir /Game/AdvancedVillagePack/Meshes]   a ue_village_build.py layout
  ue_asset_check.py --heights live.png [...]    the --heights / --old-heights / --new-heights png
  options: --report FILE (the JSON report goes there instead of stdout), --strict (warnings fail too), --project FILE (dest, size_m)

Prints one JSON report {"ok", "summary": {error, warning, info}, "assets": [{"input", "asset", "severity", "findings": [{"severity", "code",
"message", "fixable"}]}]} and a short text summary on stderr. Exit 0 = no errors, 1 = at least one error (or a warning with --strict), 2 = bad
command line. `fixable` means ue_asset_fix.py repairs it in a copy; everything else needs a person (re-download, rename in the editor, ...).
rig_copy_pack.py, ue_place_assets.py and ue_village_build.py call this as a gate and stop before they copy, connect or save.

What is checked, and why (each check is something these scripts or the documented import steps consume):
  pack     no Content folder or nothing in it to copy; .uasset/.umap that is empty or does not start with the package tag (a cut-off download:
           the editor skips it and everything that references it turns up empty); names Unreal refuses as package names (space . , & ! ~ @ # '),
           names Windows refuses (< > : " | ? * \\, trailing dot or space, CON, NUL ...: scp stops half way), names that differ only in case
           (two files on the lab, one on the rig), non-ASCII names, links, unreadable files, path longer than 259 characters under --dest,
           the same file with different bytes in two packs that merge into one folder, files changed after ue_asset_fix.py wrote them.
  sources  empty files, wrong file tag (GLB, FBX, PNG, JPG), GLB shorter than its header says, glTF buffers or images that are not there,
           node scale 0 or NaN, POSITION bounds NaN or zero, OBJ without vertices or with NaN vertices, mtllib / map_ files that are not there,
           formats with no import step (blend, stl, zip, ...), names with spaces or other characters outside A-Z a-z 0-9 _ . -
  manifest not a list, missing label / asset / x / y, duplicate labels (the second moves the first one's actor), kind other than static / skeletal
           (anything else is silently placed as static), scale 0 / NaN / Infinity (Python's json reads NaN), rotation, sink_cm, clear_foliage_cm,
           asset path not of the form /Game/Dir/Name.Name, x / y outside the map (ground_z clamps silently), asset missing from a given --pack.
  layout   the keys ue_village_build.py reads (instances, center, level_z, existing: a missing one raises after the foliage is cleared), numbers,
           mesh names, SM_<mesh> missing from a given --pack.
  heights  not a PNG, cut off, not 16-bit greyscale (an 8-bit or RGB image gives wrong ground heights; ue-mcp refuses 8-bit), sizes that differ.
"""
import argparse
import hashlib
import json
import math
import os
import re
import struct
import sys
import unicodedata
from urllib.parse import unquote

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", "..", "ansible", "roles", "watoom-code", "files", "skills", "watoom-texture-layering", "scripts")

PACKAGE_EXT = (".uasset", ".umap")
PACKAGE_SIDE_EXT = (".uexp", ".ubulk", ".uptnl")          # belong to a package of the same name: never renamed
PACKAGE_TAG = (b"\xc1\x83\x2a\x9e", b"\x9e\x2a\x83\xc1")  # 0x9E2A83C1, either byte order
UE_INVALID = set("\\:*?\"<>|' ,.&!~\n\r\t@#")             # Unreal's invalid long-package-name characters
WIN_INVALID = set('<>:"|?*\\')
WIN_RESERVED = {"con", "prn", "aux", "nul"} | {"com%d" % i for i in range(1, 10)} | {"lpt%d" % i for i in range(1, 10)}
JUNK = {".ds_store", "thumbs.db", "desktop.ini", "__macosx"}
MAX_PATH = 259
MESH_EXT = (".fbx", ".glb", ".gltf", ".obj")
NO_IMPORT_EXT = (".blend", ".stl", ".zpr", ".max", ".ma", ".mb", ".c4d", ".zip", ".rar", ".7z")
FIX_LOG = "asset_fix_log.json"
MANIFEST_KEYS = {"label", "kind", "asset", "x", "y", "scale", "rotation", "sink_cm", "clear_foliage_cm"}
ORDER = {"info": 0, "warning": 1, "error": 2}


def finding(severity, code, input_, asset, message, fixable=False):
    return {"severity": severity, "code": code, "input": input_, "asset": asset, "message": message, "fixable": fixable}


# ---------------------------------------------------------------- names

def is_junk(name):
    return name.casefold() in JUNK or name.startswith("._")


def windows_problem(name):
    """Why Windows (the rig) refuses this file or folder name, or None."""
    bad = sorted(c for c in set(name) if c in WIN_INVALID or ord(c) < 32)
    if bad:
        return "has %s" % " ".join(repr(c) for c in bad)
    if name != name.rstrip(" ."):
        return "ends with a dot or a space"
    if name.split(".")[0].casefold() in WIN_RESERVED:
        return "is a reserved device name"
    return None


def sanitise_name(name):
    """A file name with only A-Z a-z 0-9 _ . - (accents dropped, anything else and runs of it become one _). None when nothing usable is left."""
    stem, ext = os.path.splitext(name)

    def clean(s):
        s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
        return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9_.\-]", "_", s))
    stem, ext = clean(stem).rstrip(" ."), clean(ext)
    if not stem.strip("_.-") or stem.casefold() in WIN_RESERVED:
        return None
    return stem + ext


def rename_wanted(name, mode):
    """A file name the fixer should change: Windows refuses it (any mode), or a loose source file with characters outside the safe set."""
    return bool(windows_problem(name)) or (mode == "sources" and sanitise_name(name) != name)


def rename_safe(name, mode):
    """Only a name nothing else refers to may change: a mesh source file, or a non-package file of a pack. A .uasset / .umap carries its own path
    and every reference to it, and a texture / .mtl / .bin is found by name from the mesh file, so those are never renamed."""
    ext = os.path.splitext(name)[1].lower()
    if mode == "pack":
        return ext not in PACKAGE_EXT + PACKAGE_SIDE_EXT
    return ext in MESH_EXT


# ---------------------------------------------------------------- shared tree walk

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def walk(root, prefix, input_, mode, out):
    """Every regular file under root as (rel, full, size); rel starts with prefix and uses /. Adds the name, link and case findings to out."""
    files, stack = [], [(root, prefix)]
    while stack:
        d, rel_d = stack.pop()
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name)
        except OSError as e:
            out.append(finding("error", "unreadable", input_, rel_d, "cannot list the folder: %s" % e.strerror))
            continue
        seen = {}
        for e in entries:
            rel = "%s/%s" % (rel_d, e.name) if rel_d else e.name
            key = unicodedata.normalize("NFC", e.name).casefold()
            if key in seen:
                out.append(finding("error", "case_collision", input_, rel, "differs only in case from %r: one of them overwrites the other on the rig" % seen[key]))
            seen.setdefault(key, e.name)
            if is_junk(e.name):
                out.append(finding("warning", "junk_file", input_, rel, "operating-system clutter, not an asset", True))
                continue
            if e.is_symlink():
                target = os.path.realpath(e.path)
                if not os.path.exists(target):
                    out.append(finding("error", "broken_link", input_, rel, "a link to something that is not there"))
                elif os.path.commonpath([target, os.path.realpath(input_)]) != os.path.realpath(input_):
                    out.append(finding("error", "link_leaves_input", input_, rel, "a link to %s, outside this folder" % target))
                else:
                    out.append(finding("warning", "link", input_, rel, "a link: scp copies what it points to; the fixer does not copy links"))
                continue
            is_dir = e.is_dir()
            why = windows_problem(e.name)
            if why:
                ok = not is_dir and rename_safe(e.name, mode) and sanitise_name(e.name) is not None
                out.append(finding("error", "bad_name_windows", input_, rel, "the name %s: Windows refuses it and the copy to the rig stops there" % why, ok))
            elif mode == "sources" and not is_dir and sanitise_name(e.name) != e.name:
                ok = rename_safe(e.name, mode) and sanitise_name(e.name) is not None
                out.append(finding("warning", "unsafe_name", input_, rel, "the name has spaces or characters outside A-Z a-z 0-9 _ . -" +
                                   ("" if ok else " (not renamed by the fixer: a mesh file may refer to it by name)"), ok))
            if mode == "pack":
                stem = e.name if is_dir else os.path.splitext(e.name)[0]
                if is_dir or e.name.lower().endswith(PACKAGE_EXT):
                    bad = sorted(c for c in set(stem) if c in UE_INVALID)
                    if bad and not why:
                        out.append(finding("error", "bad_name_unreal", input_, rel, "the name has %s: Unreal refuses it as a package name and does not load "
                                           "the asset. Rename it in the editor of the project it came from (that fixes the references) or download it again" %
                                           " ".join(repr(c) for c in bad)))
                    if not stem.isascii():
                        out.append(finding("warning", "non_ascii_name", input_, rel, "the name is not plain ASCII: scp to Windows and Unreal can both mangle it"))
            if is_dir:
                stack.append((e.path, rel))
                continue
            try:
                size = e.stat().st_size
                if not os.access(e.path, os.R_OK):
                    raise PermissionError(13, "Permission denied")
            except OSError as err:
                out.append(finding("error", "unreadable", input_, rel, "cannot read the file: %s" % err.strerror))
                continue
            files.append((rel, e.path, size))
    return sorted(files)


def head(path, n):
    with open(path, "rb") as f:
        return f.read(n)


def check_fix_log(root, files, out):
    """A folder written by ue_asset_fix.py carries the hash of every file: anything changed, removed or added since is reported."""
    log = os.path.join(root, FIX_LOG)
    if not os.path.isfile(log):
        return
    try:
        with open(log) as f:
            listed = {c["dst"]: c for c in json.load(f)["changes"] if c.get("dst")}
    except (OSError, ValueError, KeyError, TypeError) as e:
        out.append(finding("error", "fix_log_unreadable", root, FIX_LOG, "cannot read the change log: %s" % e))
        return
    have = {rel: full for rel, full, _ in files}
    for rel, c in sorted(listed.items()):
        if rel not in have:
            out.append(finding("error", "fix_log_missing_file", root, rel, "listed in %s but not there" % FIX_LOG))
        elif sha256(have[rel]) != c.get("sha256"):
            out.append(finding("error", "hash_mismatch", root, rel, "changed since ue_asset_fix.py wrote it (sha256 differs from %s)" % FIX_LOG))
    for rel in sorted(set(have) - set(listed) - {FIX_LOG}):
        out.append(finding("warning", "not_in_fix_log", root, rel, "added after ue_asset_fix.py wrote this folder (not in %s)" % FIX_LOG))


# ---------------------------------------------------------------- packs (rig_copy_pack.py)

def scan_pack(pack, dest=None):
    """(findings, files) for one pack; files are the (rel, full, size) that rig_copy_pack.py would copy, rel relative to the pack."""
    out, files = [], []
    content = os.path.join(pack, "Content")
    if not os.path.isdir(content):
        return [finding("error", "no_content", pack, "", "no Content folder: not a UE pack, rig_copy_pack.py refuses it")], []
    tops = []
    for name in sorted(os.listdir(content)):
        if os.path.isdir(os.path.join(content, name)):
            tops.append(name)
        elif not is_junk(name):
            out.append(finding("warning", "not_copied", pack, "Content/" + name, "a file directly in Content: rig_copy_pack.py copies only the folders, so it stays behind"))
    if not tops:
        out.append(finding("error", "nothing_to_copy", pack, "Content", "Content has no folder: nothing would be copied"))
    files = walk(content, "Content", pack, "pack", out)
    files = [f for f in files if f[0].count("/") > 1]
    packages = {t: 0 for t in tops}
    other = {t: 0 for t in tops}
    for rel, full, size in files:
        top, ext = rel.split("/")[1], os.path.splitext(rel)[1].lower()
        if ext in PACKAGE_EXT:
            packages[top] += 1
            if size == 0:
                out.append(finding("error", "zero_size", pack, rel, "empty file: download the pack again"))
            else:
                try:
                    if head(full, 4) not in PACKAGE_TAG:
                        out.append(finding("error", "bad_package_tag", pack, rel, "does not start with the Unreal package tag (cut off, or not a %s): the editor skips it" % ext))
                except OSError as e:
                    out.append(finding("error", "unreadable", pack, rel, "cannot read the file: %s" % e.strerror))
        else:
            other[top] += 1
            if size == 0:
                out.append(finding("warning", "zero_size", pack, rel, "empty file"))
        if dest is not None:
            n = len(dest.rstrip("/\\")) + len(rel) - len("Content")
            if n > MAX_PATH:
                out.append(finding("error", "path_too_long", pack, rel, "%d characters under %s: over the Windows limit of %d, the copy or the editor fails on it" % (n, dest, MAX_PATH)))
    for t in tops:
        if not packages[t]:
            out.append(finding("warning", "no_packages", pack, "Content/" + t, "no .uasset or .umap in this folder: the editor will show nothing"))
        if other[t]:
            out.append(finding("info", "non_package_files", pack, "Content/" + t, "%d file(s) are not .uasset / .umap: copied, but the editor ignores them" % other[t]))
    if os.path.isfile(os.path.join(pack, FIX_LOG)):
        check_fix_log(pack, walk(pack, "", pack, "pack", []), out)
    return out, files


def check_packs(packs, dest=None):
    """Findings for every pack, plus what goes wrong when they merge into one Content folder (rig_copy_pack.py copies them in this order)."""
    out, merged, done = [], {}, set()
    for pack in packs:
        pack = pack.rstrip("/") or "/"
        if os.path.realpath(pack) in done:
            continue
        done.add(os.path.realpath(pack))
        found, files = scan_pack(pack, dest)
        out += found
        same = 0
        for rel, full, size in files:
            key = rel.casefold()
            if key not in merged:
                merged[key] = (pack, rel, full, size)
                continue
            p0, rel0, full0, size0 = merged[key]
            if rel0 != rel:
                out.append(finding("error", "case_collision", pack, rel, "is %s in %s: the two differ only in case and become one file on the rig" % (rel0, p0)))
            elif size0 != size or sha256(full0) != sha256(full):
                out.append(finding("error", "merge_conflict", pack, rel, "also in %s with different bytes: the copy from this pack overwrites that one. "
                                   "Copy the packs one at a time once you know which version the project needs" % p0))
            else:
                same += 1
        if same:
            out.append(finding("info", "shared_files", pack, "Content", "%d file(s) are also in an earlier pack with the same bytes" % same))
    return out


def package_index(packs):
    """{top folder (casefold): set of package paths 'Top/Dir/Name' (casefold)} for the .uasset / .umap of the packs."""
    index = {}
    for pack in packs:
        content = os.path.join(pack, "Content")
        for d, _, names in os.walk(content):
            for n in names:
                if n.lower().endswith(PACKAGE_EXT):
                    rel = os.path.relpath(os.path.join(d, os.path.splitext(n)[0]), content).replace(os.sep, "/")
                    index.setdefault(rel.split("/")[0].casefold(), set()).add(rel.casefold())
    return index


# ---------------------------------------------------------------- manifests and layouts

def number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def normalise_asset_path(s):
    """(the object path Unreal resolves, /Root/Dir/Name.Name; None) or (None, what is wrong). Deterministic: slashes, a leading Content/, a
    .uasset ending and a missing .Name are the only things changed."""
    if not isinstance(s, str) or not s.strip():
        return None, "is empty or not text"
    p = s.strip().replace("\\", "/")
    if p.lower().endswith(PACKAGE_EXT):
        p = p[:p.rfind(".")]
    for lead in ("Content/", "/Content/"):
        if p.startswith(lead):
            p = "/Game/" + p[len(lead):]
    if not p.startswith("/"):
        return None, "does not start with /Game/ (or another mount point)"
    pkg, _, obj = p.partition(".")
    parts = pkg.split("/")[1:]
    if len(parts) < 2 or not all(parts):
        return None, "is not /Root/Dir/Name"
    obj = obj or parts[-1]
    bad = sorted(c for c in set(pkg.replace("/", "") + obj) if c in UE_INVALID - {":"} or ord(c) < 32)
    if bad:
        return None, "has %s" % " ".join(repr(c) for c in bad)
    return pkg + "." + obj, None


def asset_findings(path, input_, who, index):
    out = []
    norm, wrong = normalise_asset_path(path)
    if wrong:
        return [finding("error", "bad_asset_path", input_, who, "asset %r %s" % (path, wrong))]
    if norm != path:
        if norm == "%s.%s" % (path, path.rsplit("/", 1)[-1]):
            out.append(finding("warning", "asset_path_short", input_, who, "asset %r has no object name; the full path is %r" % (path, norm), True))
        else:
            out.append(finding("error", "asset_path_form", input_, who, "asset %r is not an Unreal object path (the actor would get an empty mesh); it is %r" % (path, norm), True))
    if index is not None:
        pkg = norm.partition(".")[0].split("/")
        if pkg[1] == "Game" and len(pkg) > 3 and pkg[2].casefold() in index:
            if "/".join(pkg[2:]).casefold() not in index[pkg[2].casefold()]:
                out.append(finding("error", "missing_asset", input_, who, "asset %r: the given pack has Content/%s but no such .uasset in it" % (path, pkg[2])))
        else:
            out.append(finding("info", "asset_not_in_packs", input_, who, "asset %r is not in a given pack: not verified offline" % path))
    return out


def load_json(path, input_, out):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        out.append(finding("error", "unreadable", input_, "", "cannot read the JSON: %s" % e))
        return None


def check_manifest_items(items, input_="manifest", packs=(), size_m=None):
    """Findings for a ue_place_assets.py manifest that is already loaded."""
    out = []
    if not isinstance(items, list):
        return [finding("error", "bad_manifest", input_, "", "a manifest is a JSON list of items")]
    index = package_index(packs) if packs else None
    labels = {}
    for n, it in enumerate(items):
        who = "#%d" % n
        if not isinstance(it, dict):
            out.append(finding("error", "bad_item", input_, who, "is not an object"))
            continue
        lab = it.get("label")
        if not isinstance(lab, str) or not lab.strip():
            out.append(finding("error", "missing_field", input_, who, "label is missing or empty"))
        else:
            who = "#%d %s" % (n, lab.strip())
            if lab != lab.strip():
                out.append(finding("warning", "label_whitespace", input_, who, "label %r has leading or trailing whitespace" % lab, True))
            if lab.strip() in labels:
                out.append(finding("error", "duplicate_label", input_, who, "label is also item #%d: an existing actor with the label is reused, so this one moves that one" % labels[lab.strip()]))
            labels.setdefault(lab.strip(), n)
        for k in sorted(set(it) - MANIFEST_KEYS):
            out.append(finding("warning", "unknown_key", input_, who, "key %r is not read by ue_place_assets.py (a typo is silently ignored)" % k))
        kind = it.get("kind", "static")
        if kind not in ("static", "skeletal"):
            ok = isinstance(kind, str) and kind.strip().lower() in ("static", "skeletal")
            out.append(finding("error", "bad_kind", input_, who, "kind %r is not static or skeletal: it would be placed as a static mesh" % (kind,), ok))
        if "asset" not in it:
            out.append(finding("error", "missing_field", input_, who, "asset is missing"))
        else:
            out += asset_findings(it["asset"], input_, who, index)
        for k in ("x", "y"):
            if not number(it.get(k)):
                out.append(finding("error", "bad_number", input_, who, "%s is %r: a finite number is needed" % (k, it.get(k))))
            elif size_m and not 0 <= it[k] <= size_m * 100.0:
                out.append(finding("warning", "off_map", input_, who, "%s=%s cm is outside the %s m map: the ground height is taken from the map edge" % (k, it[k], size_m)))
        s = it.get("scale", 1)
        parts = [s.get(k) for k in "xyz"] if isinstance(s, dict) else [s]
        if not all(number(v) and v != 0 for v in parts):
            out.append(finding("error", "bad_scale", input_, who, "scale %r: a non-zero finite number, or {x, y, z} of them, is needed (0 or NaN gives empty bounds)" % (s,)))
        elif any(v < 0 for v in parts):
            out.append(finding("warning", "negative_scale", input_, who, "scale %r mirrors the mesh" % (s,)))
        rot = it.get("rotation", {})
        if not isinstance(rot, dict) or not all(number(v) for v in rot.values()):
            out.append(finding("error", "bad_rotation", input_, who, "rotation %r: {pitch, yaw, roll} with finite numbers is needed" % (rot,)))
        elif "rotation" in it and set(rot) != {"pitch", "yaw", "roll"}:
            out.append(finding("warning", "rotation_keys", input_, who, "rotation has keys %s, expected pitch, yaw, roll" % sorted(rot)))
        if "sink_cm" in it and not number(it["sink_cm"]):
            out.append(finding("error", "bad_number", input_, who, "sink_cm is %r: a finite number is needed" % (it["sink_cm"],)))
        r = it.get("clear_foliage_cm", 0)
        if r is not None and (not number(r) or r < 0):
            out.append(finding("error", "bad_number", input_, who, "clear_foliage_cm is %r: a finite number of 0 or more is needed" % (r,)))
    return out


def check_manifest(path, packs=(), size_m=None):
    out = []
    items = load_json(path, path, out)
    return out if out else check_manifest_items(items, path, packs, size_m)


def check_layout(path, packs=(), mesh_dir="/Game/AdvancedVillagePack/Meshes"):
    """Findings for a ue_village_build.py layout (the json unreal_village.py writes)."""
    out = []
    lay = load_json(path, path, out)
    if out:
        return out
    if not isinstance(lay, dict):
        return [finding("error", "bad_layout", path, "", "a layout is a JSON object with instances, center, level_z and existing")]
    c = lay.get("center")
    if not (isinstance(c, list) and len(c) == 2 and all(number(v) for v in c)):
        out.append(finding("error", "bad_layout", path, "center", "center is %r: [x, y] with finite numbers is needed" % (c,)))
    if not number(lay.get("level_z")):
        out.append(finding("error", "bad_layout", path, "level_z", "level_z is %r: a finite number is needed" % (lay.get("level_z"),)))
    index = package_index(packs) if packs else None
    inst = lay.get("instances")
    if not isinstance(inst, list):
        out.append(finding("error", "bad_layout", path, "instances", "instances is missing or not a list"))
        inst = []
    meshes = set()
    for n, i in enumerate(inst):
        who = "instances #%d" % n
        if not isinstance(i, dict):
            out.append(finding("error", "bad_item", path, who, "is not an object"))
            continue
        m = i.get("mesh")
        if not isinstance(m, str) or not m or any(ch in UE_INVALID or ch == "/" for ch in m):
            out.append(finding("error", "bad_mesh_name", path, who, "mesh is %r: a plain name is needed (it becomes SM_<mesh> and FT_V_<mesh>)" % (m,)))
        else:
            meshes.add(m)
        for k in ("x", "y", "yaw") + (("sink",) if "sink" in i else ()):
            if not number(i.get(k)):
                out.append(finding("error", "bad_number", path, who, "%s is %r: a finite number is needed" % (k, i.get(k))))
    for m in sorted(meshes):
        out += [f for f in asset_findings("%s/SM_%s.SM_%s" % (mesh_dir.rstrip("/"), m, m), path, "mesh " + m, index) if f["code"] != "asset_not_in_packs"]
    ex = lay.get("existing")
    if not isinstance(ex, dict):
        out.append(finding("error", "bad_layout", path, "existing", "existing is missing or not an object ({} when no actor moves): the build "
                           "reads it after the foliage is cleared"))
        ex = {}
    for lab, e in sorted(ex.items()):
        for k in ("x", "y", "yaw"):
            if not isinstance(e, dict) or not number(e.get(k)):
                out.append(finding("error", "bad_number", path, "existing " + lab, "%s is missing or not a finite number" % k))
    return out


# ---------------------------------------------------------------- heightmaps

PNG = b"\x89PNG\r\n\x1a\n"


def check_heights(*paths):
    """Findings for the heights png(s) a helper reads with numpy.asarray(Image.open(...)). Several paths must have one size."""
    out, sizes = [], {}
    for p in paths:
        try:
            h = head(p, 33)
            size = os.path.getsize(p)
            with open(p, "rb") as f:
                f.seek(max(size - 12, 0))
                tail = f.read()
        except OSError as e:
            out.append(finding("error", "unreadable", p, "", "cannot read the heights file: %s" % e.strerror))
            continue
        if not h:
            out.append(finding("error", "zero_size", p, "", "empty file"))
        elif h[:8] != PNG:
            out.append(finding("warning", "heights_not_png", p, "", "not a PNG: bit depth and size are not verified"))
        elif len(h) < 33 or h[12:16] != b"IHDR" or tail[4:8] != b"IEND":
            out.append(finding("error", "truncated", p, "", "the PNG is cut off (no complete header or no IEND at the end)"))
        else:
            w, ht, depth, colour = struct.unpack(">IIBB", h[16:26])
            if depth != 16 or colour != 0:
                out.append(finding("error", "heights_not_16bit", p, "", "%d-bit, PNG colour type %d: a 16-bit greyscale PNG is needed (anything else gives wrong "
                                   "ground heights, and ue-mcp import_heightmap refuses 8-bit). Fetch it again with ue_heights_fetch.py; it cannot be converted" % (depth, colour)))
            if w < 2 or ht < 2:
                out.append(finding("error", "heights_too_small", p, "", "%d x %d pixels: at least 2 x 2 is needed" % (w, ht)))
            elif w != ht:
                out.append(finding("warning", "heights_not_square", p, "", "%d x %d pixels: the pixel size is taken from the rows only" % (w, ht)))
            sizes[p] = (w, ht)
    if len(set(sizes.values())) > 1:
        out.append(finding("error", "heights_size_mismatch", paths[0], "", "the heights files have different sizes: %s" %
                           ", ".join("%s %dx%d" % (os.path.basename(p), s[0], s[1]) for p, s in sizes.items())))
    return out


# ---------------------------------------------------------------- loose source files

def exists_ci(folder, ref):
    """The referenced file exists; case is ignored because the import runs on Windows."""
    ref = unquote(ref).replace("\\", "/")
    full = os.path.normpath(os.path.join(folder, ref))
    if os.path.exists(full):
        return True
    try:
        return os.path.basename(full).casefold() in {n.casefold() for n in os.listdir(os.path.dirname(full))}
    except OSError:
        return False


def gltf_findings(doc, src, rel, folder):
    out = []
    if not isinstance(doc, dict):
        return [finding("error", "bad_gltf", src, rel, "the glTF JSON is not an object")]
    for kind, sev, code in (("buffers", "error", "missing_reference"), ("images", "warning", "missing_texture")):
        for b in doc.get(kind) or []:
            uri = b.get("uri") if isinstance(b, dict) else None
            if isinstance(uri, str) and not uri.startswith("data:") and not exists_ci(folder, uri):
                out.append(finding(sev, code, src, rel, "%s file %r is not there" % (kind[:-1], uri)))
    for n, node in enumerate(doc.get("nodes") or []):
        if not isinstance(node, dict):
            continue
        vals = list(node.get("scale") or []) + list(node.get("matrix") or []) + list(node.get("translation") or [])
        if not all(number(v) for v in vals) or any(v == 0 for v in node.get("scale") or []):
            out.append(finding("error", "bad_scale", src, rel, "node %d (%s) has a zero or non-finite scale / transform: it imports with empty bounds" % (n, node.get("name", ""))))
    acc = doc.get("accessors") or []
    pos = {p.get("attributes", {}).get("POSITION") for m in doc.get("meshes") or [] if isinstance(m, dict) for p in m.get("primitives") or [] if isinstance(p, dict)}
    pos = [acc[i] for i in pos if isinstance(i, int) and 0 <= i < len(acc) and isinstance(acc[i], dict)]
    if not pos:
        out.append(finding("warning", "no_geometry", src, rel, "no mesh with positions: nothing to place"))
    else:
        bounds = [(a.get("min"), a.get("max")) for a in pos if isinstance(a.get("min"), list) and isinstance(a.get("max"), list)]
        if any(not all(number(v) for v in lo + hi) for lo, hi in bounds):
            out.append(finding("error", "bad_bounds", src, rel, "a POSITION accessor has NaN or infinite bounds"))
        elif len(bounds) == len(pos) and all(lo == hi for lo, hi in bounds):
            out.append(finding("error", "zero_bounds", src, rel, "every mesh has zero-size bounds: the placed actor would have extent 0"))
    return out


def source_file_findings(src, rel, full, size, folder):
    out, ext = [], os.path.splitext(rel)[1].lower()
    if ext in NO_IMPORT_EXT:
        return [finding("warning", "no_import_step", src, rel, "%s has no import step on this route (asset.import_static_mesh takes OBJ, GLB and FBX)%s" %
                        (ext, ": unpack it first" if ext in (".zip", ".rar", ".7z") else ""))]
    if size == 0:
        return [finding("error" if ext in MESH_EXT + (".png", ".jpg", ".jpeg", ".tga", ".mtl", ".bin") else "warning", "zero_size", src, rel, "empty file")]
    try:
        if ext == ".glb":
            h = head(full, 20)
            if h[:4] != b"glTF" or len(h) < 20:
                return [finding("error", "bad_file_tag", src, rel, "does not start with the glTF tag: not a GLB")]
            total, chunk, kind = struct.unpack("<I", h[8:12])[0], struct.unpack("<I", h[12:16])[0], h[16:20]
            if total != size:
                return [finding("error", "truncated", src, rel, "the header says %d bytes, the file has %d: cut off" % (total, size))]
            if kind != b"JSON" or chunk > size:
                return [finding("error", "bad_gltf", src, rel, "the first chunk is not the JSON chunk")]
            with open(full, "rb") as f:
                f.seek(20)
                out += gltf_findings(json.loads(f.read(chunk).decode("utf-8")), src, rel, folder)
        elif ext == ".gltf":
            out += gltf_findings(json.loads(head(full, size).decode("utf-8")), src, rel, folder)
        elif ext == ".fbx":
            h = head(full, 1024)
            if not h.startswith(b"Kaydara FBX Binary") and b"FBX" not in h:
                out.append(finding("error", "bad_file_tag", src, rel, "neither a binary nor a text FBX"))
        elif ext == ".png" and head(full, 8) != PNG:
            out.append(finding("error", "bad_file_tag", src, rel, "does not start with the PNG tag"))
        elif ext in (".jpg", ".jpeg") and head(full, 2) != b"\xff\xd8":
            out.append(finding("error", "bad_file_tag", src, rel, "does not start with the JPEG tag"))
        elif ext in (".obj", ".mtl"):
            verts, bad = 0, 0
            with open(full, "rb") as f:
                for line in f:
                    word = line.split(None, 1)
                    if len(word) < 2:
                        continue
                    key, rest = word[0].lower(), word[1].strip().decode("utf-8", "replace")
                    if key == b"v":
                        verts += 1
                        low = rest.lower()
                        bad += "nan" in low or "inf" in low
                    elif key == b"mtllib" and not exists_ci(folder, rest):
                        out.append(finding("warning", "missing_reference", src, rel, "mtllib %r is not there: it imports without materials" % rest))
                    elif ext == ".mtl" and (key.startswith(b"map_") or key in (b"bump", b"disp", b"norm")):
                        if not exists_ci(folder, rest) and not exists_ci(folder, rest.split()[-1]):
                            out.append(finding("warning", "missing_texture", src, rel, "%s %r is not there" % (key.decode(), rest)))
            if ext == ".obj" and not verts:
                out.append(finding("error", "no_geometry", src, rel, "no vertex lines: nothing to import"))
            if bad:
                out.append(finding("error", "bad_bounds", src, rel, "%d vertex line(s) with NaN or infinity" % bad))
    except (OSError, ValueError, struct.error) as e:
        out.append(finding("error", "unreadable", src, rel, "cannot parse the file: %s" % e))
    return out


def check_sources(src):
    """Findings for a folder of loose downloads (FBX / GLB / glTF / OBJ and their textures) that are imported file by file."""
    out = []
    if not os.path.isdir(src):
        return [finding("error", "unreadable", src, "", "not a folder")]
    files = walk(src, "", src, "sources", out)
    for rel, full, size in files:
        if rel != FIX_LOG:
            out += source_file_findings(src, rel, full, size, os.path.dirname(full))
    if not any(os.path.splitext(rel)[1].lower() in MESH_EXT for rel, _, _ in files):
        out.append(finding("info", "no_mesh_files", src, "", "no FBX, GLB, glTF or OBJ here"))
    check_fix_log(src, files, out)
    return out


# ---------------------------------------------------------------- report and gate

def report(findings, strict=False):
    assets, count = {}, {"error": 0, "warning": 0, "info": 0}
    for f in findings:
        count[f["severity"]] += 1
        a = assets.setdefault((f["input"], f["asset"]), {"input": f["input"], "asset": f["asset"], "severity": "info", "findings": []})
        a["findings"].append({k: f[k] for k in ("severity", "code", "message", "fixable")})
        a["severity"] = max(a["severity"], f["severity"], key=ORDER.get)
    ok = not count["error"] and not (strict and count["warning"])
    return {"tool": "ue_asset_check", "schema": 1, "ok": ok, "summary": count, "assets": [assets[k] for k in sorted(assets)]}


def gate(findings, what, stream=None, limit=30):
    """Print the errors and warnings and return True when the caller must stop (there is an error). The one call the pipeline scripts make."""
    stream = stream or sys.stderr
    shown = sorted((f for f in findings if f["severity"] != "info"), key=lambda f: (-ORDER[f["severity"]], f["input"], f["asset"]))
    for f in shown[:limit]:
        print("asset check %s: %s %s: %s [%s]" % (f["severity"].upper(), os.path.basename(f["input"].rstrip("/")), f["asset"], f["message"], f["code"]), file=stream)
    if len(shown) > limit:
        print("asset check: ... and %d more (ue_asset_check.py prints all of them as JSON)" % (len(shown) - limit), file=stream)
    errors = sum(f["severity"] == "error" for f in findings)
    if errors:
        fixable = sum(f["severity"] == "error" and f["fixable"] for f in findings)
        print("asset check FAILED for %s: %d error(s), %d of them repairable in a copy with ue_asset_fix.py. Nothing was copied, changed or saved." % (what, errors, fixable), file=stream)
    return bool(errors)


def main(argv=None):
    sys.path.insert(0, SKILL)
    import ue_project
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pack", action="append", default=[], help="a downloaded UE pack (the folder that holds Content)")
    ap.add_argument("--sources", action="append", default=[], help="a folder of loose FBX / GLB / glTF / OBJ / texture files")
    ap.add_argument("--manifest", action="append", default=[], help="a ue_place_assets.py manifest")
    ap.add_argument("--layout", action="append", default=[], help="a ue_village_build.py layout")
    ap.add_argument("--heights", action="append", default=[], help="a heights png")
    ap.add_argument("--dest", default=None, help="rig project Content folder: enables the path length check")
    ap.add_argument("--size-m", type=float, default=None, help="map edge in metres: enables the off-map check")
    ap.add_argument("--mesh-dir", default="/Game/AdvancedVillagePack/Meshes")
    ap.add_argument("--report", default=None, help="write the JSON report here instead of stdout")
    ap.add_argument("--strict", action="store_true", help="a warning fails too")
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    if not (a.pack or a.sources or a.manifest or a.layout or a.heights):
        ap.error("nothing to check: give --pack, --sources, --manifest, --layout or --heights")
    found = check_packs(a.pack, a.dest) if a.pack else []
    for s in a.sources:
        found += check_sources(s.rstrip("/") or "/")
    for m in a.manifest:
        found += check_manifest(m, a.pack, a.size_m)
    for lay in a.layout:
        found += check_layout(lay, a.pack, a.mesh_dir)
    if a.heights:
        found += check_heights(*a.heights)
    rep = report(found, a.strict)
    text = json.dumps(rep, indent=1)
    if a.report:
        with open(a.report, "w") as f:
            f.write(text + "\n")
    else:
        print(text)
    print("asset check %s: %d error(s), %d warning(s), %d note(s) on %d asset(s)" % ("ok" if rep["ok"] else "FAILED", rep["summary"]["error"],
          rep["summary"]["warning"], rep["summary"]["info"], len(rep["assets"])), file=sys.stderr)
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
