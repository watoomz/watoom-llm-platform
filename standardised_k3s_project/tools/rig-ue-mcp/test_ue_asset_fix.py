"""ue_asset_fix.py: dry run by default, a new copy and a change log on --apply, the original never touched, unsafe repairs refused."""
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_asset_check as ck
import ue_asset_fix as fx
from test_ue_asset_check import GOOD_GLTF, TAG, glb, put, read


def tree(**files):
    d = os.path.join(tempfile.mkdtemp(), "src")
    for rel, data in files.items():
        put(d, rel, data)
    return d


def snapshot(root):
    """{relative path: (sha256, mtime_ns)} of everything under root (or of the one file)."""
    if os.path.isfile(root):
        return {"": (hashlib.sha256(read(root)).hexdigest(), os.stat(root).st_mtime_ns)}
    return {os.path.relpath(os.path.join(d, n), root): (hashlib.sha256(read(os.path.join(d, n))).hexdigest(), os.stat(os.path.join(d, n)).st_mtime_ns)
            for d, _, names in os.walk(root) for n in names}


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        rc = fx.main(argv)
    return rc, json.loads(out.getvalue())


def listing(root):
    return sorted(os.path.relpath(os.path.join(d, n), root) for d, _, names in os.walk(root) for n in names)


class Sources(unittest.TestCase):
    def src(self):
        return tree(**{"Model+#5.glb": glb(GOOD_GLTF), "My Tree.obj": "mtllib tree.mtl\nv 0 0 0\n", "tree.mtl": "newmtl a\n", "sub/ok.fbx": b"Kaydara FBX Binary",
                       ".DS_Store": b"x", "__MACOSX/._Model": b"x"})

    def test_dry_run_is_the_default_and_writes_nothing(self):
        s = self.src()
        out = s + "_fixed"
        before = snapshot(s)
        for extra in ([], ["--dry-run"], ["--apply", "--dry-run"]):
            rc, res = run(["sources", s, "--out", out] + extra)
            self.assertEqual(rc, 0, extra)
            self.assertFalse(res["applied"])
            self.assertIn("dry run", res["note"])
            self.assertEqual(sorted((c["action"], c["src"], c["dst"]) for c in res["changes"]),
                             [("drop", ".DS_Store", None), ("drop", "__MACOSX/", None), ("rename", "Model+#5.glb", "Model_5.glb"), ("rename", "My Tree.obj", "My_Tree.obj")])
            self.assertEqual(res["unchanged_files"], 2)
            self.assertFalse(os.path.exists(out) or os.path.exists(out + ".partial"))
        self.assertEqual(snapshot(s), before)

    def test_apply_writes_a_new_copy_with_a_log_and_leaves_the_original(self):
        s = self.src()
        out = s + "_fixed"
        before = snapshot(s)
        rc, res = run(["sources", s, "--out", out, "--apply"])
        self.assertEqual(rc, 0)
        self.assertTrue(res["applied"])
        self.assertEqual(res["recheck"]["error"], 0)
        self.assertEqual(snapshot(s), before)                                   # same bytes, same mtimes
        self.assertEqual(listing(out), ["Model_5.glb", "My_Tree.obj", ck.FIX_LOG, "sub/ok.fbx", "tree.mtl"])
        self.assertEqual(read(os.path.join(out, "Model_5.glb")), glb(GOOD_GLTF))
        log = json.loads(read(os.path.join(out, ck.FIX_LOG)))
        self.assertEqual(log["source"], os.path.abspath(s))
        by = {c["src"]: c for c in log["changes"]}
        self.assertEqual((by["Model+#5.glb"]["action"], by["Model+#5.glb"]["dst"]), ("rename", "Model_5.glb"))
        self.assertEqual(by["Model+#5.glb"]["sha256"], hashlib.sha256(glb(GOOD_GLTF)).hexdigest())
        self.assertEqual((by["sub/ok.fbx"]["action"], by[".DS_Store"]["action"]), ("copy", "drop"))
        self.assertEqual([f["code"] for f in ck.check_sources(out) if f["severity"] != "info"], [])    # deterministic: a second pass has nothing to do
        rc, res = run(["sources", out, "--out", out + "2"])
        self.assertEqual((rc, res["changes"]), (0, []))

    def test_an_existing_output_is_never_overwritten(self):
        s = self.src()
        for out in (put(tempfile.mkdtemp(), "taken/keep.txt", b"mine")[:-len("/keep.txt")], os.path.join(s, "inside"), os.path.dirname(s)):
            before = snapshot(out) if os.path.isdir(out) else None
            rc, res = run(["sources", s, "--out", out, "--apply"])
            self.assertEqual((rc, res["applied"]), (1, False), out)
            self.assertIn("bad_out", [r["code"] for r in res["refused"]])
            if before is not None:
                self.assertEqual(snapshot(out), before)

    def test_unsafe_and_ambiguous_repairs_are_refused_and_nothing_is_written(self):
        cases = {
            "rename_collision": {"a b.fbx": b"Kaydara FBX Binary", "a_b.fbx": b"Kaydara FBX Binary"},      # two names, one result
            "bad_name_windows": {"wood:bark.png": ck.PNG, "m.fbx": b"Kaydara FBX Binary"},                 # a texture is found by name
            "zero_size": {"empty.fbx": b""},                                                               # needs a new download
            "truncated": {"cut.glb": glb(GOOD_GLTF)[:-4]},
            "case_collision": {"Tree.fbx": b"Kaydara FBX Binary", "tree.fbx": b"Kaydara FBX Binary"},
        }
        for code, files in cases.items():
            s = tree(**files)
            out = s + "_fixed"
            before = snapshot(s)
            rc, res = run(["sources", s, "--out", out, "--apply"])
            self.assertEqual((rc, res["applied"]), (1, False), code)
            self.assertIn(code, [r["code"] for r in res["refused"]], code)
            self.assertIn("nothing written", res["note"])
            self.assertFalse(os.path.exists(out) or os.path.exists(out + ".partial"), code)
            self.assertEqual(snapshot(s), before)

    def test_a_name_with_nothing_usable_and_a_referenced_texture_are_left_alone(self):
        s = tree(**{"木.fbx": b"Kaydara FBX Binary", "wood bark.png": ck.PNG})
        rc, res = run(["sources", s, "--out", s + "_fixed", "--apply"])
        self.assertEqual((rc, res["changes"]), (0, []))                         # warnings only: copied as they are, and reported
        self.assertEqual(sorted(w["asset"] for w in res["left_as_is"]), ["wood bark.png", "木.fbx"])
        self.assertEqual(listing(s + "_fixed"), sorted([ck.FIX_LOG, "wood bark.png", "木.fbx"]))

    def test_links_are_refused(self):
        s = tree(**{"a.fbx": b"Kaydara FBX Binary"})
        os.symlink(os.path.join(s, "a.fbx"), os.path.join(s, "b.fbx"))
        rc, res = run(["sources", s, "--out", s + "_fixed", "--apply"])
        self.assertEqual(rc, 1)
        self.assertIn("link_not_copied", [r["code"] for r in res["refused"]])


class Pack(unittest.TestCase):
    def test_a_package_or_folder_with_a_bad_name_is_never_renamed(self):
        for files in ({"Content/Pk/SM My Mesh.uasset": TAG}, {"Content/Pk/My Folder/SM_A.uasset": TAG}, {"Content/Pk/SM_A:1.uasset": TAG}, {"Content/Pk/SM_Cut.uasset": b"<html>"}):
            s = tree(**files)
            rc, res = run(["pack", s, "--out", s + "_fixed", "--apply"])
            self.assertEqual((rc, res["applied"], res["changes"]), (1, False, []), files)
            self.assertFalse(os.path.exists(s + "_fixed"))

    def test_clutter_is_dropped_and_a_non_package_name_is_repaired_then_the_copy_passes_the_gate(self):
        s = tree(**{"Content/Pk/SM_A.uasset": TAG, "Content/Pk/Thumbs.db": b"x", "Content/Pk/notes?.txt": b"n", "Config/Default.ini": b"[x]"})
        self.assertIn("bad_name_windows", [f["code"] for f in ck.check_packs([s]) if f["severity"] == "error"])
        before = snapshot(s)
        rc, res = run(["pack", s, "--out", s + "_fixed", "--apply"])
        self.assertEqual(rc, 0)
        self.assertEqual(snapshot(s), before)
        self.assertEqual(listing(s + "_fixed"), ["Config/Default.ini", "Content/Pk/SM_A.uasset", "Content/Pk/notes_.txt", ck.FIX_LOG])
        self.assertEqual([f for f in ck.check_packs([s + "_fixed"]) if f["severity"] != "info"], [])

    def test_the_checker_verifies_a_fixed_copy_against_its_log(self):
        s = tree(**{"Content/Pk/SM_A.uasset": TAG, "Content/Pk/SM_B.uasset": TAG, "Content/Pk/Thumbs.db": b"x"})
        out = s + "_fixed"
        self.assertEqual(run(["pack", s, "--out", out, "--apply"])[0], 0)
        with open(os.path.join(out, "Content", "Pk", "SM_A.uasset"), "ab") as f:
            f.write(b"changed later")
        os.remove(os.path.join(out, "Content", "Pk", "SM_B.uasset"))
        put(out, "Content/Pk/SM_New.uasset", TAG)
        got = sorted((f["asset"], f["severity"], f["code"]) for f in ck.check_packs([out]) if f["severity"] != "info")
        self.assertEqual(got, [("Content/Pk/SM_A.uasset", "error", "hash_mismatch"), ("Content/Pk/SM_B.uasset", "error", "fix_log_missing_file"),
                               ("Content/Pk/SM_New.uasset", "warning", "not_in_fix_log")])


class Manifest(unittest.TestCase):
    ITEMS = [{"label": " Tower ", "kind": "Static", "asset": "Content\\Pk\\SM_Tower.uasset", "x": 1, "y": 2, "scale": 60},
             {"label": "Robot", "kind": "skeletal", "asset": "/Game/Pk/SK_Robot", "x": 3, "y": 4}]

    def manifest(self, items):
        return put(tempfile.mkdtemp(), "m.json", json.dumps(items))

    def test_dry_run_then_apply_writes_a_new_manifest_and_a_log(self):
        m = self.manifest(self.ITEMS)
        out = os.path.join(tempfile.mkdtemp(), "fixed.json")
        before = snapshot(m)
        rc, res = run(["manifest", m, "--out", out])
        self.assertEqual((rc, res["applied"], len(res["changes"])), (0, False, 4))
        self.assertFalse(os.path.exists(out))
        rc, res = run(["manifest", m, "--out", out, "--apply"])
        self.assertEqual((rc, res["applied"], res["recheck"]["error"]), (0, True, 0))
        self.assertEqual(snapshot(m), before)
        self.assertEqual(json.loads(read(out)), [{"label": "Tower", "kind": "static", "asset": "/Game/Pk/SM_Tower.SM_Tower", "x": 1, "y": 2, "scale": 60},
                                                {"label": "Robot", "kind": "skeletal", "asset": "/Game/Pk/SK_Robot.SK_Robot", "x": 3, "y": 4}])
        log = json.loads(read(out + ".fixlog.json"))
        self.assertEqual([(c["item"], c["field"], c["before"], c["after"]) for c in log["changes"]],
                         [(0, "label", " Tower ", "Tower"), (0, "kind", "Static", "static"), (0, "asset", "Content\\Pk\\SM_Tower.uasset", "/Game/Pk/SM_Tower.SM_Tower"),
                          (1, "asset", "/Game/Pk/SK_Robot", "/Game/Pk/SK_Robot.SK_Robot")])
        self.assertEqual(log["output_sha256"], hashlib.sha256(read(out)).hexdigest())
        self.assertEqual(ck.check_manifest(out), [])
        self.assertEqual(run(["manifest", m, "--out", out, "--apply"])[0], 1)   # the output exists now: refused, not overwritten

    def test_problems_that_need_a_decision_are_refused(self):
        good = {"label": "A", "asset": "/Game/P/SM_A.SM_A", "x": 1, "y": 2}
        for code, items in (("bad_scale", [dict(good, scale=0)]), ("duplicate_label", [good, dict(good)]), ("missing_field", [{"label": "A", "x": 1, "y": 2}]),
                            ("bad_kind", [dict(good, kind="rigged")]), ("bad_asset_path", [dict(good, asset="SM A")]), ("bad_manifest", {"label": "A"})):
            out = os.path.join(tempfile.mkdtemp(), "fixed.json")
            rc, res = run(["manifest", self.manifest(items), "--out", out, "--apply"])
            self.assertEqual((rc, res["applied"]), (1, False), code)
            self.assertIn(code, [r["code"] for r in res["refused"]], code)
            self.assertFalse(os.path.exists(out) or os.path.exists(out + ".fixlog.json"), code)

    def test_whitespace_labels_that_collide_after_the_trim_are_refused(self):
        good = {"label": "A", "asset": "/Game/P/SM_A.SM_A", "x": 1, "y": 2}
        rc, res = run(["manifest", self.manifest([good, dict(good, label="A ")]), "--out", os.path.join(tempfile.mkdtemp(), "f.json"), "--apply"])
        self.assertEqual(rc, 1)
        self.assertIn("duplicate_label", [r["code"] for r in res["refused"]])


if __name__ == "__main__":
    unittest.main()
