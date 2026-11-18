"""ue_asset_check.py: every check on a small made-up tree (no rig, no editor, no network), and the gate in the three pipeline scripts."""
import contextlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
import zlib
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig_copy_pack
import ue_asset_check as ck
import ue_place_assets
import ue_route
import ue_village_build

TAG = b"\xc1\x83\x2a\x9e" + b"\0" * 60
DEST = "F:/Proj/Content/"


def put(root, rel, data=TAG):
    f = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, "wb") as h:
        h.write(data if isinstance(data, bytes) else data.encode())
    return f


def pack(**files):
    d = tempfile.mkdtemp()
    for rel, data in (files or {"Content/Pk/Meshes/SM_A.uasset": TAG}).items():
        put(d, rel, data)
    return d


def png(path, w, h, depth=16, colour=0, cut=False):
    """A valid PNG written by hand (the checker reads only the header and the end, like these bytes)."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\0" + b"\0" * (w * (depth // 8) * (3 if colour == 2 else 1)) for _ in range(h))
    data = ck.PNG + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, colour, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(data[:-20] if cut else data)
    return path


def read(path, mode="rb"):
    with open(path, mode) as f:
        return f.read()


def codes(found, severity=None):
    return sorted(f["code"] for f in found if severity in (None, f["severity"]))


def glb(doc):
    body = json.dumps(doc).encode()
    body += b" " * (-len(body) % 4)
    return b"glTF" + struct.pack("<II", 2, 20 + len(body)) + struct.pack("<I", len(body)) + b"JSON" + body


GOOD_GLTF = {"nodes": [{"name": "n", "scale": [1, 1, 1]}], "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
             "accessors": [{"min": [0, 0, 0], "max": [1, 2, 3]}]}


class Pack(unittest.TestCase):
    def test_a_good_pack_has_no_errors_or_warnings(self):
        found = ck.check_packs([pack()], DEST)
        self.assertEqual(codes(found, "error") + codes(found, "warning"), [])
        self.assertTrue(ck.report(found)["ok"])

    def test_no_content_and_nothing_to_copy(self):
        self.assertEqual(codes(ck.check_packs([tempfile.mkdtemp()])), ["no_content"])
        self.assertIn("nothing_to_copy", codes(ck.check_packs([pack(**{"Content/stray.uasset": TAG})]), "error"))

    def test_empty_and_cut_off_packages_are_errors(self):
        found = ck.check_packs([pack(**{"Content/Pk/SM_Empty.uasset": b"", "Content/Pk/SM_Cut.uasset": b"<html>not found", "Content/Pk/L.umap": TAG,
                                        "Content/Pk/readme.txt": b""})])
        by = {f["asset"]: (f["severity"], f["code"]) for f in found if f["code"] in ("zero_size", "bad_package_tag")}
        self.assertEqual(by, {"Content/Pk/SM_Empty.uasset": ("error", "zero_size"), "Content/Pk/SM_Cut.uasset": ("error", "bad_package_tag"),
                              "Content/Pk/readme.txt": ("warning", "zero_size")})

    def test_names_unreal_or_windows_refuse(self):
        found = ck.check_packs([pack(**{"Content/Pk/SM My Mesh.uasset": TAG, "Content/Pk/My Folder/SM_B.uasset": TAG, "Content/Pk/SM_C:1.uasset": TAG,
                                        "Content/Pk/notes?.txt": b"x", "Content/Pk/SM_Caf\u00e9.uasset": TAG, "Content/Pk/con.uasset": TAG})])
        by = {f["asset"]: f for f in found if f["code"].startswith("bad_name") or f["code"] == "non_ascii_name"}
        self.assertEqual(by["Content/Pk/SM My Mesh.uasset"]["code"], "bad_name_unreal")
        self.assertEqual(by["Content/Pk/My Folder"]["code"], "bad_name_unreal")
        self.assertFalse(by["Content/Pk/SM My Mesh.uasset"]["fixable"])          # a package is never renamed
        self.assertEqual((by["Content/Pk/SM_C:1.uasset"]["code"], by["Content/Pk/SM_C:1.uasset"]["fixable"]), ("bad_name_windows", False))
        self.assertEqual((by["Content/Pk/notes?.txt"]["code"], by["Content/Pk/notes?.txt"]["fixable"]), ("bad_name_windows", True))
        self.assertEqual(by["Content/Pk/con.uasset"]["code"], "bad_name_windows")
        self.assertEqual((by["Content/Pk/SM_Caf\u00e9.uasset"]["severity"], by["Content/Pk/SM_Caf\u00e9.uasset"]["code"]), ("warning", "non_ascii_name"))

    def test_case_collision_in_one_pack_and_between_packs(self):
        self.assertIn("case_collision", codes(ck.check_packs([pack(**{"Content/Pk/SM_A.uasset": TAG, "Content/Pk/sm_a.uasset": TAG})]), "error"))
        found = ck.check_packs([pack(**{"Content/Pk/SM_A.uasset": TAG}), pack(**{"Content/pk/SM_A.uasset": TAG})])
        self.assertIn("case_collision", codes(found, "error"))

    def test_packs_that_merge_identical_files_are_fine_and_different_bytes_are_not(self):
        a, same, other = pack(), pack(), pack(**{"Content/Pk/Meshes/SM_A.uasset": TAG + b"v2"})
        found = ck.check_packs([a, same])
        self.assertEqual(codes(found, "error"), [])
        self.assertIn("shared_files", codes(found, "info"))
        self.assertEqual(codes(ck.check_packs([a, other]), "error"), ["merge_conflict"])
        self.assertEqual(codes(ck.check_packs([a, a + "/"]), "info"), [])                # the same pack twice is one pack

    def test_path_length_needs_the_destination(self):
        p = pack(**{"Content/Pk/" + "D" * 100 + "/" + "E" * 100 + "/SM_" + "F" * 60 + ".uasset": TAG})
        self.assertNotIn("path_too_long", codes(ck.check_packs([p])))
        self.assertIn("path_too_long", codes(ck.check_packs([p], DEST), "error"))

    def test_links_junk_and_folders_without_packages(self):
        p = pack(**{"Content/Pk/SM_A.uasset": TAG, "Content/Pk/.DS_Store": b"x", "Content/Docs/readme.txt": b"x"})
        os.symlink("/nonexistent/x", os.path.join(p, "Content", "Pk", "SM_Gone.uasset"))
        os.symlink("/etc/hostname", os.path.join(p, "Content", "Pk", "SM_Out.uasset"))
        os.symlink(os.path.join(p, "Content", "Pk", "SM_A.uasset"), os.path.join(p, "Content", "Pk", "SM_In.uasset"))
        by = {f["asset"]: (f["severity"], f["code"], f["fixable"]) for f in ck.check_packs([p])}
        self.assertEqual(by["Content/Pk/SM_Gone.uasset"][:2], ("error", "broken_link"))
        self.assertEqual(by["Content/Pk/SM_Out.uasset"][:2], ("error", "link_leaves_input"))
        self.assertEqual(by["Content/Pk/SM_In.uasset"][:2], ("warning", "link"))
        self.assertEqual(by["Content/Pk/.DS_Store"], ("warning", "junk_file", True))
        self.assertIn(("Content/Docs", "warning", "no_packages"), [(f["asset"], f["severity"], f["code"]) for f in ck.check_packs([p])])

    @unittest.skipIf(os.geteuid() == 0, "root reads every file")
    def test_unreadable_file(self):
        p = pack()
        os.chmod(os.path.join(p, "Content", "Pk", "Meshes", "SM_A.uasset"), 0)
        self.assertIn("unreadable", codes(ck.check_packs([p]), "error"))


class Sources(unittest.TestCase):
    def tree(self, **files):
        d = tempfile.mkdtemp()
        for rel, data in files.items():
            put(d, rel, data)
        return d

    def test_good_files_pass(self):
        d = self.tree(**{"model.glb": glb(GOOD_GLTF), "tree.obj": "mtllib tree.mtl\nv 0 0 0\nv 1 1 1\n", "tree.mtl": "newmtl a\nmap_Kd Bark.PNG\n",
                         "bark.png": ck.PNG + b"x", "man.fbx": b"Kaydara FBX Binary  \0rest"})
        found = ck.check_sources(d)
        self.assertEqual(codes(found, "error") + codes(found, "warning"), [])       # Bark.PNG matches bark.png: the import runs on Windows

    def test_broken_files(self):
        cut = glb(GOOD_GLTF)[:-8]
        d = self.tree(**{"empty.fbx": b"", "html.fbx": b"<html>", "cut.glb": cut, "not.glb": b"PK\x03\x04" + b"0" * 30, "bad.png": b"GIF89a", "bad.jpg": b"\x89PNG",
                         "nan.obj": "v 0 0 0\nv nan 1 1\n", "none.obj": "# nothing\n", "tree.obj": "mtllib gone.mtl\nv 0 0 0\n", "t.mtl": "map_Kd gone.png\n",
                         "scene.blend": b"BLENDER", "pack.zip": b"PK"})
        by = {f["asset"]: (f["severity"], f["code"]) for f in ck.check_sources(d)}
        self.assertEqual(by, {"empty.fbx": ("error", "zero_size"), "html.fbx": ("error", "bad_file_tag"), "cut.glb": ("error", "truncated"),
                              "not.glb": ("error", "bad_file_tag"), "bad.png": ("error", "bad_file_tag"), "bad.jpg": ("error", "bad_file_tag"),
                              "nan.obj": ("error", "bad_bounds"), "none.obj": ("error", "no_geometry"), "tree.obj": ("warning", "missing_reference"),
                              "t.mtl": ("warning", "missing_texture"), "scene.blend": ("warning", "no_import_step"), "pack.zip": ("warning", "no_import_step")})

    def test_gltf_references_scale_and_bounds(self):
        zero = dict(GOOD_GLTF, nodes=[{"scale": [1, 0, 1]}])
        nan = dict(GOOD_GLTF, nodes=[{"scale": [1, float("nan"), 1]}])
        flat = dict(GOOD_GLTF, accessors=[{"min": [1, 1, 1], "max": [1, 1, 1]}])
        inf = dict(GOOD_GLTF, accessors=[{"min": [0, 0, 0], "max": [float("inf"), 1, 1]}])
        refs = dict(GOOD_GLTF, buffers=[{"uri": "gone.bin"}, {"uri": "data:application/octet-stream;base64,AA=="}, {"uri": "there.bin"}], images=[{"uri": "tex%20a.png"}, {"uri": "gone.png"}])
        d = self.tree(**{"zero.glb": glb(zero), "nan.glb": glb(nan), "flat.gltf": json.dumps(flat), "inf.gltf": json.dumps(inf), "refs.gltf": json.dumps(refs),
                         "there.bin": b"x", "tex a.png": ck.PNG, "empty.gltf": "{}"})
        got = sorted((f["asset"], f["severity"], f["code"]) for f in ck.check_sources(d) if f["code"] != "unsafe_name")
        self.assertEqual(got, [("empty.gltf", "warning", "no_geometry"), ("flat.gltf", "error", "zero_bounds"), ("inf.gltf", "error", "bad_bounds"),
                               ("nan.glb", "error", "bad_scale"), ("refs.gltf", "error", "missing_reference"), ("refs.gltf", "warning", "missing_texture"),
                               ("zero.glb", "error", "bad_scale")])

    def test_unsafe_names_only_mesh_files_are_fixable(self):
        d = self.tree(**{"Model+#5.glb": glb(GOOD_GLTF), "wood bark.png": ck.PNG, "ok_name-1.fbx": b"Kaydara FBX Binary"})
        by = {f["asset"]: (f["severity"], f["code"], f["fixable"]) for f in ck.check_sources(d)}
        self.assertEqual(by, {"Model+#5.glb": ("warning", "unsafe_name", True), "wood bark.png": ("warning", "unsafe_name", False)})

    def test_sanitise_name(self):
        self.assertEqual(ck.sanitise_name("Model+#5.glb"), "Model_5.glb")
        self.assertEqual(ck.sanitise_name("Caf\u00e9 du  Nord (v2).FBX"), "Cafe_du_Nord_v2_.FBX")
        self.assertEqual(ck.sanitise_name("already_ok-1.v2.obj"), "already_ok-1.v2.obj")
        self.assertIsNone(ck.sanitise_name("\u6728.fbx"))        # nothing usable is left: a person names it
        self.assertIsNone(ck.sanitise_name("con.fbx"))


class Manifest(unittest.TestCase):
    ITEM = {"label": "Tower", "kind": "static", "asset": "/Game/Pk/Meshes/SM_A.SM_A", "x": 4000, "y": 4000, "scale": 60,
            "rotation": {"pitch": 0, "yaw": 0, "roll": 90}, "sink_cm": 30, "clear_foliage_cm": 500}

    def check(self, *items, **kw):
        return ck.check_manifest_items(list(items), "m", **kw)

    def test_a_good_item(self):
        self.assertEqual(self.check(self.ITEM, {"label": "B", "asset": "/Game/X/SK_B.SK_B", "kind": "skeletal", "x": 0, "y": 0, "scale": {"x": 1, "y": 1, "z": 2}}, size_m=4000), [])

    def test_shape_and_missing_fields(self):
        self.assertEqual(codes(ck.check_manifest_items({"label": "x"})), ["bad_manifest"])
        self.assertEqual(codes(self.check("text", {})), ["bad_item", "bad_number", "bad_number", "missing_field", "missing_field"])

    def test_duplicate_labels_kind_and_unknown_keys(self):
        found = self.check(self.ITEM, dict(self.ITEM, kind="Skeletal"), dict(self.ITEM, label="T2", kind="rigged", clear_foliage=5))
        self.assertEqual(sorted((f["asset"], f["code"], f["fixable"]) for f in found),
                         [("#1 Tower", "bad_kind", True), ("#1 Tower", "duplicate_label", False), ("#2 T2", "bad_kind", False), ("#2 T2", "unknown_key", False)])

    def test_numbers_scale_and_rotation(self):
        nan = json.loads('{"s": NaN, "i": Infinity}')        # Python's json reads these
        bad = [dict(self.ITEM, label="a", scale=0), dict(self.ITEM, label="b", scale=nan["s"]), dict(self.ITEM, label="c", scale={"x": 1, "y": 1}),
               dict(self.ITEM, label="d", scale={"x": 1, "y": 0, "z": 1}), dict(self.ITEM, label="e", x=nan["i"]), dict(self.ITEM, label="f", y="12"),
               dict(self.ITEM, label="g", rotation={"pitch": 0, "yaw": nan["s"], "roll": 0}), dict(self.ITEM, label="h", sink_cm=None),
               dict(self.ITEM, label="i", clear_foliage_cm=-1), dict(self.ITEM, label="j", scale=True)]
        found = self.check(*bad)
        self.assertEqual([f["code"] for f in found], ["bad_scale"] * 4 + ["bad_number"] * 2 + ["bad_rotation"] + ["bad_number"] * 2 + ["bad_scale"])
        self.assertTrue(all(f["severity"] == "error" and not f["fixable"] for f in found))
        warn = self.check(dict(self.ITEM, scale=-1, x=999999, rotation={"yaw": 5}), size_m=4000)
        self.assertEqual(codes(warn, "warning"), ["negative_scale", "off_map", "rotation_keys"])
        self.assertEqual(codes(warn, "error"), [])

    def test_asset_paths(self):
        self.assertEqual(ck.normalise_asset_path("/Game/A/SM_B"), ("/Game/A/SM_B.SM_B", None))
        self.assertEqual(ck.normalise_asset_path(" \\Game\\A\\SM_B.uasset "), ("/Game/A/SM_B.SM_B", None))
        self.assertEqual(ck.normalise_asset_path("Content/A/SM_B.uasset"), ("/Game/A/SM_B.SM_B", None))
        self.assertEqual(ck.normalise_asset_path("/Game/A/BP_X.BP_X_C"), ("/Game/A/BP_X.BP_X_C", None))
        for wrong in ("", None, "SM_B", "/Game", "/Game//SM_B", "/Game/A/SM B", "C:/x/SM_B.fbx"):
            self.assertIsNone(ck.normalise_asset_path(wrong)[0], wrong)
        by = {f["asset"]: (f["severity"], f["code"], f["fixable"]) for f in
              self.check(dict(self.ITEM, label="a", asset="/Game/A/SM_B"), dict(self.ITEM, label="b", asset="Content/A/SM_B.uasset"), dict(self.ITEM, label="c", asset="SM_B"))}
        self.assertEqual(by, {"#0 a": ("warning", "asset_path_short", True), "#1 b": ("error", "asset_path_form", True), "#2 c": ("error", "bad_asset_path", False)})

    def test_asset_is_looked_up_in_a_given_pack(self):
        p = pack()
        found = self.check(self.ITEM, dict(self.ITEM, label="b", asset="/Game/Pk/Meshes/SM_Gone.SM_Gone"), dict(self.ITEM, label="c", asset="/Game/Other/SM_A.SM_A"),
                           dict(self.ITEM, label="d", asset="/game/pk/meshes/sm_a.SM_A"), packs=[p])
        self.assertEqual(sorted((f["asset"], f["severity"], f["code"]) for f in found), [("#1 b", "error", "missing_asset"), ("#2 c", "info", "asset_not_in_packs"),
                                                                                       ("#3 d", "info", "asset_not_in_packs")])

    def test_unreadable_manifest_file(self):
        f = put(tempfile.mkdtemp(), "m.json", "[{")
        self.assertEqual(codes(ck.check_manifest(f), "error"), ["unreadable"])
        self.assertEqual(codes(ck.check_manifest(f + ".missing"), "error"), ["unreadable"])


class Layout(unittest.TestCase):
    GOOD = {"center": [4000, 4000], "level_z": 7000, "instances": [{"mesh": "Well", "x": 4000, "y": 4000, "yaw": 0}], "existing": {"House_1": {"x": 5000, "y": 5000, "yaw": 0}}}

    def check(self, lay, **kw):
        return ck.check_layout(put(tempfile.mkdtemp(), "l.json", json.dumps(lay)), **kw)

    def test_good_layout(self):
        self.assertEqual(self.check(self.GOOD), [])

    def test_missing_keys_and_bad_values(self):
        self.assertEqual(codes(self.check({"instances": []})), ["bad_layout"] * 3)       # center, level_z, existing
        bad = dict(self.GOOD, instances=[{"mesh": "My Well", "x": 1, "y": 1, "yaw": 0}, {"mesh": "Well", "x": float("nan"), "y": 1}, {"mesh": "W", "x": 1, "y": 1, "yaw": 0, "sink": "a"}],
                   existing={"H": {"x": 1}})
        self.assertEqual(codes(self.check(bad)), ["bad_mesh_name"] + ["bad_number"] * 5)

    def test_mesh_is_looked_up_in_a_given_pack(self):
        p = pack(**{"Content/AdvancedVillagePack/Meshes/SM_Well.uasset": TAG})
        self.assertEqual(self.check(self.GOOD, packs=[p]), [])
        lay = dict(self.GOOD, instances=[{"mesh": "Barn", "x": 1, "y": 1, "yaw": 0}])
        self.assertEqual(codes(self.check(lay, packs=[p])), ["missing_asset"])


class Heights(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def f(self, name):
        return os.path.join(self.d, name)

    def test_16_bit_grey_passes_and_matches_what_pillow_writes(self):
        self.assertEqual(ck.check_heights(png(self.f("a.png"), 20, 20)), [])
        import numpy as np
        from PIL import Image
        Image.fromarray(np.full((20, 20), 1234, np.uint16)).save(self.f("pil.png"))      # the way ue_heights_fetch.py writes it
        self.assertEqual(ck.check_heights(self.f("pil.png")), [])
        Image.fromarray(np.full((20, 20), 12, np.uint8)).save(self.f("pil8.png"))
        self.assertEqual(codes(ck.check_heights(self.f("pil8.png")), "error"), ["heights_not_16bit"])

    def test_wrong_depth_colour_size_and_cut_off(self):
        self.assertEqual(codes(ck.check_heights(png(self.f("8.png"), 20, 20, depth=8)), "error"), ["heights_not_16bit"])
        self.assertEqual(codes(ck.check_heights(png(self.f("rgb.png"), 20, 20, colour=2)), "error"), ["heights_not_16bit"])
        self.assertEqual(codes(ck.check_heights(png(self.f("cut.png"), 20, 20, cut=True)), "error"), ["truncated"])
        self.assertEqual(codes(ck.check_heights(png(self.f("one.png"), 1, 1)), "error"), ["heights_too_small"])
        self.assertEqual(codes(ck.check_heights(png(self.f("wide.png"), 30, 20))), ["heights_not_square"])
        self.assertEqual(codes(ck.check_heights(png(self.f("a.png"), 20, 20), png(self.f("b.png"), 40, 40)), "error"), ["heights_size_mismatch"])
        open(self.f("empty.png"), "w").close()
        self.assertEqual(codes(ck.check_heights(self.f("empty.png"), self.f("missing.png")), "error"), ["unreadable", "zero_size"])
        self.assertEqual(codes(ck.check_heights(put(self.d, "h.tif", b"II*\0rest")), "warning"), ["heights_not_png"])


class Cli(unittest.TestCase):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = ck.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_json_report_severity_per_asset_and_exit_code(self):
        p = pack(**{"Content/Pk/SM_A.uasset": TAG, "Content/Pk/SM_Empty.uasset": b"", "Content/Pk/.DS_Store": b"x"})
        rc, out, err = self.run_main(["--pack", p])
        rep = json.loads(out)
        self.assertEqual(rc, 1)
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["summary"], {"error": 1, "warning": 1, "info": 0})
        self.assertEqual({a["asset"]: a["severity"] for a in rep["assets"]}, {"Content/Pk/SM_Empty.uasset": "error", "Content/Pk/.DS_Store": "warning"})
        self.assertEqual(rep["assets"][1]["findings"][0]["code"], "zero_size")
        self.assertIn("FAILED", err)

    def test_clean_input_exits_zero_strict_fails_on_a_warning_and_report_file(self):
        p = pack(**{"Content/Pk/SM_A.uasset": TAG, "Content/Pk/.DS_Store": b"x"})
        self.assertEqual(self.run_main(["--pack", p])[0], 0)
        self.assertEqual(self.run_main(["--pack", p, "--strict"])[0], 1)
        f = os.path.join(tempfile.mkdtemp(), "r.json")
        rc, out, _ = self.run_main(["--pack", pack(), "--heights", png(os.path.join(tempfile.mkdtemp(), "h.png"), 8, 8), "--report", f])
        self.assertEqual((rc, out), (0, ""))
        self.assertTrue(json.loads(read(f))["ok"])

    def test_nothing_to_check_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stderr(io.StringIO()):
            ck.main([])
        self.assertEqual(e.exception.code, 2)

    def test_the_checker_writes_nothing(self):
        p = pack(**{"Content/Pk/SM_A.uasset": TAG, "Content/Pk/bad name.uasset": b""})
        before = sorted((d, sorted(n), [os.stat(os.path.join(d, x)).st_mtime_ns for x in sorted(n)]) for d, _, n in os.walk(p))
        self.run_main(["--pack", p, "--dest", DEST])
        self.assertEqual(before, sorted((d, sorted(n), [os.stat(os.path.join(d, x)).st_mtime_ns for x in sorted(n)]) for d, _, n in os.walk(p)))


class Gate(unittest.TestCase):
    """A bad asset stops the pipeline scripts with exit 1 before they copy, connect or save."""

    def quiet(self, fn, *a):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = fn(*a)
        return rc, out.getvalue(), err.getvalue()

    def test_rig_copy_pack_copies_nothing_from_a_bad_pack(self):
        good, bad = pack(), pack(**{"Content/Pk2/SM_Cut.uasset": b"<html>"})
        ran = []
        fake = lambda cmd, **kw: ran.append(cmd) or type("R", (), {"returncode": 0})()
        with mock.patch.object(rig_copy_pack.subprocess, "run", fake):
            for extra in ([], ["--apply"]):
                rc, out, err = self.quiet(rig_copy_pack.main, [good, bad, "--dest", DEST] + extra)
                self.assertEqual(rc, 1, extra)
                self.assertEqual(ran, [], extra)                 # not even the good pack: the run is all or nothing
                self.assertNotIn("scp", out)
                self.assertIn("bad_package_tag", err)
                self.assertIn("asset check FAILED", err)
            rc, out, err = self.quiet(rig_copy_pack.main, [good, bad, "--dest", DEST, "--apply", "--no-asset-check"])
            self.assertEqual((rc, len(ran)), (0, 2))
            ran.clear()
            rc, out, err = self.quiet(rig_copy_pack.main, [good, "--dest", DEST, "--apply"])
            self.assertEqual((rc, len(ran), err), (0, 1, ""))

    def test_rig_copy_pack_checks_the_path_length_under_dest(self):
        p = pack(**{"Content/Pk/" + "D" * 120 + "/SM_A.uasset": TAG})
        self.assertEqual(self.quiet(rig_copy_pack.main, [p, "--dest", DEST])[0], 0)
        rc, _, err = self.quiet(rig_copy_pack.main, [p, "--dest", "F:/" + "P" * 140 + "/Content/"])
        self.assertEqual(rc, 1)
        self.assertIn("path_too_long", err)

    def heights(self, depth=16):
        return png(os.path.join(tempfile.mkdtemp(), "h.png"), 20, 20, depth=depth)

    def no_route(self):
        def boom(*a, **k):
            raise AssertionError("the editor route was opened")
        return mock.patch.object(ue_route, "SshTransport", boom)

    def test_place_assets_stops_before_the_route_on_a_bad_manifest_or_heights(self):
        d = tempfile.mkdtemp()
        item = {"label": "Tower", "asset": "/Game/SM_Tower.SM_Tower", "x": 4000, "y": 4000}
        zero = put(d, "zero.json", json.dumps([dict(item, scale=0)]))
        dup = put(d, "dup.json", json.dumps([item, item]))
        ok = put(d, "ok.json", json.dumps([item]))
        tail = ["--z0", "3677.7", "--raw-per-cm", "4.4387", "--size-m", "152"]
        with self.no_route():
            for m, h, code in ((zero, self.heights(), "bad_scale"), (dup, self.heights(), "duplicate_label"), (ok, self.heights(8), "heights_not_16bit")):
                for extra in ([], ["--dry-run"], ["--force-save"]):
                    rc, out, err = self.quiet(ue_place_assets.main, [m, "--heights", h] + tail + extra)
                    self.assertEqual(rc, 1, (code, extra))
                    self.assertIn(code, err)
                    self.assertIn("asset check FAILED", err)
            self.assertEqual(self.quiet(ue_place_assets.main, [ok, "--heights", self.heights(), "--dry-run"] + tail)[0], 0)

    def test_village_build_stops_before_the_route_on_a_bad_layout_or_heights(self):
        d = tempfile.mkdtemp()
        good = dict(Layout.GOOD)
        missing = put(d, "missing.json", json.dumps({k: v for k, v in good.items() if k != "existing"}))
        ok = put(d, "ok.json", json.dumps(good))
        tail = ["--z0", "3677.7", "--raw-per-cm", "4.4387", "--size-m", "152"]
        big = png(os.path.join(d, "big.png"), 40, 40)
        with self.no_route():
            for lay, new, code in ((missing, self.heights(), "bad_layout"), (ok, self.heights(8), "heights_not_16bit"), (ok, big, "heights_size_mismatch")):
                rc, out, err = self.quiet(ue_village_build.main, [lay, "--old-heights", self.heights(), "--new-heights", new, "--apply", "--force-save"] + tail)
                self.assertEqual(rc, 1, code)
                self.assertIn(code, err)
            self.assertEqual(self.quiet(ue_village_build.main, [ok, "--old-heights", self.heights(), "--new-heights", self.heights()] + tail)[0], 0)


if __name__ == "__main__":
    unittest.main()
