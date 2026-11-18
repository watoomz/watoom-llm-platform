import json, pathlib, subprocess, sys, tempfile, unittest
HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import blender_job_spec as spec
import game_blender
import game_worker_bridge as bridge


class BlenderJob(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.project = pathlib.Path(self.tmp.name)
        (self.project / 'scripts').mkdir();(self.project / 'scripts/go.py').write_text('print(1)')

    def tearDown(self): self.tmp.cleanup()

    def write(self, value):
        d = self.project / '.opencode/blender-jobs/j';d.mkdir(parents=True, exist_ok=True)
        (d / 'request.json').write_text(value if isinstance(value, str) else json.dumps(value))

    def test_project_and_skill_scripts(self):
        self.write({'schema': 1, 'script': 'scripts/go.py', 'args': ['--out', '{out}']})
        v = spec.load(self.project, 'j');self.assertEqual((v['deadline_sec'], v['memory_gib']), (300, 4))
        self.write({'schema': 1, 'script': 'skill:blender-export-pipelines/scripts/fbx_relink_to_glb.py'})
        self.assertTrue(spec.load(self.project, 'j')['script'].is_file())

    def test_errors_name_the_field(self):
        for bad, field in [({'schema': 1, 'script': '../x.py'}, 'script'), ({'schema': 1, 'script': '/etc/passwd'}, 'script'),
                           ({'schema': 1, 'script': 'skill:../../x.py'}, 'script'), ({'schema': 1, 'script': 'skill:none/scripts/x.py'}, 'installed skill'),
                           ({'schema': 1, 'script': 'scripts/missing.py'}, 'regular .py'), ({'schema': 1, 'script': 'scripts/go.py', 'args': [1]}, 'args'),
                           ({'schema': 1, 'script': 'scripts/go.py', 'memory_gib': 16}, 'memory_gib'), ({'schema': 1, 'script': 'scripts/go.py', 'deadline_sec': 5000}, 'deadline_sec'),
                           ({'schema': 1, 'script': 'scripts/go.py', 'shell': 'x'}, 'unknown fields'), ({'schema': 1}, 'script')]:
            self.write(bad)
            with self.assertRaisesRegex(ValueError, field): spec.load(self.project, 'j')
        current, reason = bridge.checked_fingerprint(self.project, {'operation': 'blender', 'job': 'j'})
        self.assertIsNone(current);self.assertIn('.opencode/blender-jobs/j/request.json', reason)

    def test_blend_and_skill_memory_rules(self):
        (self.project / '.opencode/blender-out/a').mkdir(parents=True);(self.project / '.opencode/blender-out/a/x.blend').write_bytes(b'BLENDER')
        self.write({'schema': 1, 'blend': '.opencode/blender-out/a/x.blend', 'script': 'scripts/go.py'})
        self.assertTrue(spec.load(self.project, 'j')['blend'].is_file())
        for bad, field in [({'schema': 1, 'blend': 'missing.blend', 'script': 'scripts/go.py'}, 'blend'),
                           ({'schema': 1, 'blend': '../x.blend', 'script': 'scripts/go.py'}, 'blend'),
                           ({'schema': 1, 'script': 'skill:blender-asset-qa/scripts/qa_check.py', 'memory_gib': 6}, 'memory_gib must be 4')]:
            self.write(bad)
            with self.assertRaisesRegex(ValueError, field): spec.load(self.project, 'j')

    def test_route_uses_the_skills_qualified_profile(self):
        self.assertEqual(game_blender.BLENDER_SHA, game_blender.PROFILE['sha256']);self.assertTrue(game_blender.BLENDER.is_file())

    def test_guard_and_dispatcher_agree(self):
        self.write({'schema': 1, 'script': 'scripts/go.py'})
        guard = HERE.parent.parent / 'ansible/roles/watoom-code/files/coordinator-guard/index.js'
        js = subprocess.check_output(['node', '--input-type=module', '-e', 'const m=await import(process.argv[1]);console.log(await m.blenderJobFingerprint(process.argv[2],"j"))', str(guard), str(self.project)], text=True).strip()
        self.assertEqual(js, bridge.request_fingerprint(self.project, {'operation': 'blender', 'job': 'j'}))

    def test_diagnose_reports_traceback_and_result(self):
        log = 'Blender 5.2.3\n@@JSON@@{"ok": false}\nTraceback (most recent call last):\n  File "x.py", line 3, in <module>\n    boom()\nNameError: name \'boom\' is not defined\nBlender quit\n'
        tb, errors, result = game_blender.diagnose(log)
        self.assertEqual(tb[-1], "NameError: name 'boom' is not defined");self.assertEqual(result, {'ok': False})
        big = '@@JSON@@' + json.dumps({'ok': True, 'results': ['x' * 100] * 200})
        self.assertNotIn('results', game_blender.diagnose(big)[2])


if __name__ == '__main__': unittest.main()
