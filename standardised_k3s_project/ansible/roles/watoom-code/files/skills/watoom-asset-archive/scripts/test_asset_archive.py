import argparse
import io
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
import asset_archive as aa


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.assets = os.path.join(self.root, "assets")
        self.projects = os.path.join(self.root, "projects")
        self.proj = os.path.join(self.projects, "games", "demo")
        os.makedirs(self.assets)
        os.makedirs(self.proj)
        self.pol = aa.Policy(
            source_roots=[self.assets], project_root=self.projects, global_queue=os.path.join(self.root, "queue")
        )

    def tearDown(self):
        self.tmp.cleanup()

    def zip(self, name="pack.zip", files=None, build=None):
        path = os.path.join(self.assets, name)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            if build:
                build(z)
            for n, data in (files or {}).items():
                z.writestr(n, data)
        return path

    def call(self, op, archive, **kw):
        a = aa.args_from_dict(dict(op=op, archive=archive, **kw))
        return aa.run(a, self.pol)

    def codes(self, out, key="errors"):
        return {e["code"] for e in out[key]}


class ZipTests(Base):
    FILES = {
        "Pack/Models/tree.glb": b"glb" * 100,
        "Pack/Textures/bark.png": b"png" * 50,
        "Pack/Textures/leaf.jpg": b"jpg" * 40,
        "Pack/readme.txt": b"hello\n",
        "Pack/Sounds/wind.wav": b"w" * 10,
        "__MACOSX/._x": b"junk",
        "Pack/.DS_Store": b"junk",
    }

    def test_list_filters_and_ignores_mac_junk(self):
        out = self.call("list", self.zip(files=self.FILES), select=["Pack/Textures/**"])
        self.assertTrue(out["ok"])
        self.assertEqual(["Pack/Textures/bark.png", "Pack/Textures/leaf.jpg"], [e["path"] for e in out["entries"]])
        self.assertEqual(2, out["junk_skipped"])
        allof = self.call("list", self.zip(files=self.FILES))
        self.assertEqual(5, allof["matched"]["files"])

    def test_inspect_summarises_and_deep_test_passes(self):
        out = self.call("inspect", self.zip(files=self.FILES), test=True)
        self.assertTrue(out["ok"], out["errors"])
        self.assertEqual({"files": 5, "bad": 0}, out["inspect"]["tested"])
        self.assertEqual("Pack", out["inspect"]["top_folders"][0][0])

    def test_read_text_and_binary(self):
        z = self.zip(files=self.FILES)
        t = self.call("read", z, entry="Pack/readme.txt")
        self.assertEqual("hello\n", t["entry"]["text"])
        b = self.call("read", z, entry="Pack/Models/tree.glb")
        self.assertTrue(b["ok"] and "text" in b["entry"])  # no NUL bytes in this fixture
        n = self.call("read", z, entry="Pack/missing.txt")
        self.assertFalse(n["ok"])
        self.assertIn("ENTRY_NOT_FOUND", self.codes(n))
        cut = self.call("read", z, entry="Pack/Models/tree.glb", max_bytes=10)
        self.assertTrue(cut["entry"]["truncated"] and cut["entry"]["bytes_returned"] == 10)

    def test_extract_subset_strip_and_receipt(self):
        z = self.zip(files=self.FILES)
        out = self.call("extract", z, project=self.proj, select=["Pack/Textures/**"], strip=1, dest="Assets/pack")
        self.assertTrue(out["ok"], out["errors"])
        self.assertEqual(2, out["extracted"]["files"])
        self.assertTrue(os.path.isfile(os.path.join(self.proj, "Assets/pack/Textures/bark.png")))
        self.assertFalse(os.path.exists(os.path.join(self.proj, "Assets/pack/Models")))
        self.assertTrue(os.path.isfile(os.path.join(self.proj, out["receipt"])))
        self.assertFalse([f for f in pathlib.Path(self.proj).rglob("*") if ".part-" in f.name])

    def test_default_dest_and_second_run_is_unchanged_not_error(self):
        z = self.zip("My Pack.zip", self.FILES)
        a = self.call("extract", z, project="demo")
        self.assertTrue(a["ok"], a["errors"])
        self.assertTrue(os.path.isdir(os.path.join(self.proj, "Assets/My Pack")))
        b = self.call("extract", z, project=self.proj)
        self.assertTrue(b["ok"])
        self.assertEqual(0, b["extracted"]["files"])
        self.assertEqual(5, b["extracted"]["unchanged"])

    def test_conflict_needs_overwrite(self):
        z = self.zip(files={"a.txt": b"new"})
        os.makedirs(os.path.join(self.proj, "Assets/pack"))
        pathlib.Path(self.proj, "Assets/pack/a.txt").write_bytes(b"old!")
        out = self.call("extract", z, project=self.proj, dest="Assets/pack")
        self.assertFalse(out["ok"])
        self.assertIn("DEST_CONFLICT", self.codes(out))
        self.assertEqual(b"old!", pathlib.Path(self.proj, "Assets/pack/a.txt").read_bytes())
        ok = self.call("extract", z, project=self.proj, dest="Assets/pack", overwrite=True)
        self.assertTrue(ok["ok"])
        self.assertEqual(b"new", pathlib.Path(self.proj, "Assets/pack/a.txt").read_bytes())

    def test_dry_run_writes_nothing(self):
        out = self.call("extract", self.zip(files=self.FILES), project=self.proj, dry_run=True)
        self.assertTrue(out["ok"] and out["dry_run"])
        self.assertFalse(os.path.exists(os.path.join(self.proj, "Assets")))


class UnsafeArchiveTests(Base):
    def test_traversal_absolute_and_drive_paths_are_flagged_and_never_written(self):
        z = self.zip(
            files={"ok.txt": b"fine", "../evil.txt": b"x", "/abs.txt": b"x", "C:/win.txt": b"x", "a/../../up.txt": b"x"}
        )
        out = self.call("extract", z, project=self.proj, dest="Assets/p", partial_ok=True)
        self.assertFalse(out["ok"])
        self.assertEqual({"UNSAFE_NAME"}, self.codes(out))
        self.assertEqual(4, len(out["errors"]))
        self.assertTrue(os.path.isfile(os.path.join(self.proj, "Assets/p/ok.txt")))
        for bad in ("evil.txt", "abs.txt", "win.txt", "up.txt"):
            self.assertFalse(list(pathlib.Path(self.root).rglob(bad)), bad)

    def test_without_partial_ok_nothing_is_extracted_when_any_error(self):
        z = self.zip(files={"ok.txt": b"fine", "../evil.txt": b"x"})
        out = self.call("extract", z, project=self.proj, dest="Assets/p")
        self.assertFalse(out["ok"])
        self.assertFalse(os.path.exists(os.path.join(self.proj, "Assets/p/ok.txt")))

    def test_symlink_entries_are_skipped_with_warning(self):
        def build(z):
            i = zipfile.ZipInfo("link")
            i.create_system = 3
            i.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(i, "/etc/passwd")
            z.writestr("real.txt", b"x")

        out = self.call("extract", self.zip(build=build), project=self.proj, dest="Assets/p")
        self.assertTrue(out["ok"])
        self.assertIn("UNSUPPORTED_ENTRY_TYPE", self.codes(out, "warnings"))
        self.assertFalse(os.path.lexists(os.path.join(self.proj, "Assets/p/link")))

    def test_case_clash_is_an_error(self):
        out = self.call("extract", self.zip(files={"Tex/Bark.png": b"1", "tex/bark.png": b"2"}), project=self.proj)
        self.assertFalse(out["ok"])
        self.assertIn("CASE_CLASH", self.codes(out))

    def test_encrypted_entry_is_flagged(self):
        def build(z):
            i = zipfile.ZipInfo("secret.bin")
            z.writestr(i, b"data")
            z.filelist[-1].flag_bits |= 1

        out = self.call("extract", self.zip(build=build), project=self.proj)
        self.assertFalse(out["ok"])
        self.assertIn("ENCRYPTED_ENTRY", self.codes(out))

    def test_destination_restrictions(self):
        z = self.zip(files={"a.txt": b"x"})
        for dest in ("../out", "/tmp/x", ".godot/x", "Assets/.opencode/y", ""):
            out = self.call("extract", z, project=self.proj, dest=dest or ".")
            self.assertFalse(out["ok"], dest)
            self.assertIn("DEST_NOT_ALLOWED", self.codes(out))
        os.makedirs(os.path.join(self.root, "elsewhere"))
        os.symlink(os.path.join(self.root, "elsewhere"), os.path.join(self.proj, "Assets"))
        out = self.call("extract", z, project=self.proj, dest="Assets/p")
        self.assertFalse(out["ok"])
        self.assertIn("DEST_NOT_ALLOWED", self.codes(out))
        self.assertFalse(os.listdir(os.path.join(self.root, "elsewhere")))

    def test_project_and_archive_must_be_inside_allowed_roots(self):
        z = self.zip(files={"a.txt": b"x"})
        out = self.call("extract", z, project=self.root)
        self.assertFalse(out["ok"])
        self.assertIn("PROJECT_NOT_ALLOWED", self.codes(out))
        outside = os.path.join(self.root, "outside.zip")
        shutil.copy(z, outside)
        out = self.call("list", outside)
        self.assertFalse(out["ok"])
        self.assertIn("ARCHIVE_NOT_ALLOWED", self.codes(out))
        out = self.call("list", os.path.join(self.assets, "nope.zip"))
        self.assertIn("ARCHIVE_NOT_FOUND", self.codes(out))

    def test_bomb_and_size_limits(self):
        pol = aa.Policy(
            source_roots=[self.assets],
            project_root=self.projects,
            limits={"bomb_min_bytes": 1000, "bomb_ratio": 20, "max_total_bytes": 10**9},
        )
        z = self.zip(files={"zeros.bin": b"\0" * 5_000_000})
        a = aa.args_from_dict(dict(op="extract", archive=z, project=self.proj))
        out = aa.run(a, pol)
        self.assertFalse(out["ok"])
        self.assertIn("BOMB_SUSPECT", self.codes(out))
        self.assertFalse(os.path.exists(os.path.join(self.proj, "Assets")))
        a = aa.args_from_dict(dict(op="extract", archive=z, project=self.proj, force_large=True))
        self.assertTrue(aa.run(a, pol)["ok"])


class CorruptionTests(Base):
    def test_truncated_zip_is_reported_as_unreadable(self):
        z = self.zip(files={"a.bin": os.urandom(200000)})
        data = open(z, "rb").read()
        open(z, "wb").write(data[: len(data) // 2])
        out = self.call("list", z)
        self.assertFalse(out["ok"])
        self.assertIn("ARCHIVE_UNREADABLE", self.codes(out))
        self.assertIn("truncated", out["errors"][0]["message"])

    def test_flipped_bytes_give_crc_error_and_no_partial_file(self):
        payload = os.urandom(50000)
        z = self.zip(files={"good.bin": b"ok" * 10, "bad.bin": payload})
        raw = bytearray(open(z, "rb").read())
        idx = raw.find(payload[:16]) if raw.find(payload[:16]) >= 0 else None
        if idx is None:  # deflated random data is stored almost as-is; corrupt the middle of the bad entry
            info = zipfile.ZipFile(z).getinfo("bad.bin")
            idx = info.header_offset + 60 + len("bad.bin") + 100
        raw[idx + 10] ^= 0xFF
        open(z, "wb").write(bytes(raw))
        out = self.call("extract", z, project=self.proj, dest="Assets/p", partial_ok=True)
        self.assertFalse(out["ok"])
        self.assertTrue({"CRC_MISMATCH", "ENTRY_CORRUPT"} & self.codes(out), out["errors"])
        self.assertTrue(os.path.isfile(os.path.join(self.proj, "Assets/p/good.bin")))
        self.assertFalse(os.path.exists(os.path.join(self.proj, "Assets/p/bad.bin")))
        self.assertFalse([f for f in pathlib.Path(self.proj).rglob("*") if ".part-" in f.name])
        t = self.call("inspect", z, test=True)
        self.assertFalse(t["ok"])

    def test_unknown_format(self):
        p = os.path.join(self.assets, "x.dat")
        open(p, "wb").write(b"not an archive" * 10)
        out = self.call("list", p)
        self.assertFalse(out["ok"])
        self.assertIn("UNSUPPORTED_FORMAT", self.codes(out))


class TarTests(Base):
    def test_tar_gz_list_select_extract(self):
        p = os.path.join(self.assets, "p.tar.gz")
        with tarfile.open(p, "w:gz") as t:
            for n, d in {"p/a.txt": b"aaa", "p/sub/b.txt": b"bbb", "p/c.png": b"ccc"}.items():
                i = tarfile.TarInfo(n)
                i.size = len(d)
                t.addfile(i, io.BytesIO(d))
            ln = tarfile.TarInfo("p/link")
            ln.type = tarfile.SYMTYPE
            ln.linkname = "/etc/passwd"
            t.addfile(ln)
        self.assertEqual(3, self.call("list", p)["matched"]["files"])
        out = self.call("extract", p, project=self.proj, ext="txt", strip=1, dest="Assets/t")
        self.assertTrue(out["ok"], out["errors"])
        self.assertEqual(2, out["extracted"]["files"])
        self.assertTrue(os.path.isfile(os.path.join(self.proj, "Assets/t/sub/b.txt")))
        self.assertIn("UNSUPPORTED_ENTRY_TYPE", self.codes(self.call("list", p), "warnings"))


@unittest.skipUnless(shutil.which("7z"), "7z not installed")
class SevenZipTests(Base):
    def make(self):
        src = os.path.join(self.root, "src")
        os.makedirs(os.path.join(src, "Pack/Tex"))
        os.makedirs(os.path.join(src, "Pack/Mesh"))
        pathlib.Path(src, "Pack/Tex/a.png").write_bytes(b"a" * 4000)
        pathlib.Path(src, "Pack/Mesh/m [1].glb").write_bytes(b"m" * 3000)
        pathlib.Path(src, "Pack/notes.txt").write_text("hi")
        out = os.path.join(self.assets, "pack.7z")
        subprocess.run(["7z", "a", "-bd", out, "Pack"], cwd=src, check=True, capture_output=True)
        return out

    def test_list_read_extract_subset_with_special_characters(self):
        z = self.make()
        l = self.call("list", z)
        self.assertTrue(l["ok"], l)
        self.assertEqual(3, l["matched"]["files"])
        self.assertEqual("hi", self.call("read", z, entry="Pack/notes.txt")["entry"]["text"])
        out = self.call("extract", z, project=self.proj, prefix="Pack/Mesh", dest="Assets/seven", strip=1)
        self.assertTrue(out["ok"], out["errors"])
        self.assertEqual(1, out["extracted"]["files"])
        self.assertTrue(os.path.isfile(os.path.join(self.proj, "Assets/seven/Mesh/m [1].glb")))
        self.assertFalse(os.path.exists(os.path.join(self.proj, "Assets/seven/Tex")))
        self.assertFalse(
            os.path.exists(os.path.join(self.proj, ".opencode/tmp"))
            and os.listdir(os.path.join(self.proj, ".opencode/tmp"))
        )

    def test_second_run_with_everything_unchanged_is_ok(self):
        z = self.make()
        first = self.call("extract", z, project=self.proj, dest="Assets/seven")
        second = self.call("extract", z, project=self.proj, dest="Assets/seven")
        self.assertTrue(first["ok"] and second["ok"], second)
        self.assertEqual((0, 3), (second["extracted"]["files"], second["extracted"]["unchanged"]))

    def test_corrupt_7z_is_reported(self):
        z = self.make()
        raw = bytearray(open(z, "rb").read())
        raw[len(raw) // 2] ^= 0xFF
        open(z, "wb").write(bytes(raw))
        out = self.call("extract", z, project=self.proj, dest="Assets/bad", partial_ok=True)
        self.assertFalse(out["ok"], out)

    def test_host_worker_queue_round_trip(self):
        z = self.make()
        real = shutil.which
        aa.shutil.which = lambda n: None if n in ("7z", "7za", "7zz") else real(n)  # behave like the pod
        try:
            a = aa.args_from_dict(dict(op="list", archive=z))
            a.wait = 1
            pending = aa.run(a, self.pol)
            self.assertTrue(pending.get("pending"), pending)
        finally:
            aa.shutil.which = real
        self.assertEqual(1, aa.serve_once(self.pol, [self.pol.global_queue]))
        res = aa.find_result(self.pol, pending["id"])
        self.assertTrue(res["ok"], res)
        self.assertEqual("host-worker", res["via"])
        self.assertEqual(3, res["matched"]["files"])

    def test_project_queue_request_cannot_target_another_project(self):
        z = self.make()
        other = os.path.join(self.projects, "games", "other")
        os.makedirs(other)
        q = os.path.join(self.proj, aa.PROJECT_QUEUE)
        os.makedirs(q)
        rid = "ar-20260101000000-abcdef"
        json.dump(
            {"schema": 1, "id": rid, "op": "extract", "archive": z, "project": other},
            open(os.path.join(q, rid + ".request.json"), "w"),
        )
        aa.serve_once(self.pol, [q])
        res = json.load(open(os.path.join(q, rid + ".result.json")))
        self.assertFalse(res["ok"])
        self.assertEqual("PROJECT_NOT_ALLOWED", res["errors"][0]["code"])
        self.assertFalse(os.path.exists(os.path.join(other, "Assets")))


class UnrarParserTests(unittest.TestCase):
    SAMPLE = """UNRAR 7.23 freeware

Archive: /x/a.rar
Details: RAR 5

        Name: Content/Tex/bark.png
        Type: File
        Size: 2048
 Packed size: 900
       Ratio: 43%
       CRC32: 14A285AC
     Host OS: Windows

        Name: Content/Tex
        Type: Directory
        Size: 0

        Name: Content/link
        Type: Unix symbolic link
        Size: 12

        Name: Content/secret.bin
        Type: File
        Size: 10
       CRC32: 00000001
       Flags: encrypted

"""

    def test_blocks_become_entries(self):
        b = aa.UnrarBackend.__new__(aa.UnrarBackend)
        b.out = self.SAMPLE
        es = list(b.entries())
        self.assertEqual(["file", "dir", "link", "file"], [e.kind for e in es])
        self.assertEqual((2048, 0x14A285AC, False), (es[0].size, es[0].crc, es[0].encrypted))
        self.assertTrue(es[3].encrypted)
        res = aa.Result("list")

        class FB:
            def entries(self_):
                return iter(es)

        kept = aa.load_entries(FB(), res)
        self.assertEqual(["Content/Tex/bark.png"], [e.name for e in kept])
        self.assertEqual({"UNSUPPORTED_ENTRY_TYPE"}, {w["code"] for w in res.d["warnings"]})
        self.assertEqual({"ENCRYPTED_ENTRY"}, {e["code"] for e in res.d["errors"]})


class WorkerRejectsBadRequests(Base):
    def test_bad_id_oversized_and_unknown_op(self):
        q = self.pol.global_queue
        os.makedirs(q)
        json.dump(
            {"op": "delete", "id": "ar-20260101000000-abcdef"},
            open(os.path.join(q, "ar-20260101000000-abcdef.request.json"), "w"),
        )
        json.dump({"op": "list", "archive": "x", "id": "evil"}, open(os.path.join(q, "evil.request.json"), "w"))
        open(os.path.join(q, "ar-20260101000001-abcdef.request.json"), "w").write(
            '{"op":"list","pad":"' + "x" * 70000 + '"}'
        )
        self.assertEqual(3, aa.serve_once(self.pol, [q]))
        for n in ("ar-20260101000000-abcdef", "evil", "ar-20260101000001-abcdef"):
            self.assertFalse(json.load(open(os.path.join(q, n + ".result.json")))["ok"], n)
        self.assertEqual(0, aa.serve_once(self.pol, [q]))  # already answered


class CliTests(Base):
    def test_cli_prints_json_and_exit_codes(self):
        z = self.zip(files={"a.txt": b"x"})
        env = dict(
            os.environ,
            WATOOM_ARCHIVE_SOURCE_ROOTS=self.assets,
            WATOOM_ARCHIVE_PROJECT_ROOT=self.projects,
            WATOOM_ARCHIVE_QUEUE=self.pol.global_queue,
        )
        ok = subprocess.run([sys.executable, aa.__file__, "list", z], capture_output=True, text=True, env=env)
        self.assertEqual(0, ok.returncode)
        self.assertTrue(json.loads(ok.stdout)["ok"])
        bad = subprocess.run(
            [sys.executable, aa.__file__, "list", os.path.join(self.assets, "missing.zip")],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(1, bad.returncode)
        self.assertFalse(json.loads(bad.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
