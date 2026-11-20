import json, os, pathlib, subprocess, sys, tempfile, unittest
from unittest import mock
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import game_godot_game as O


class Pure(unittest.TestCase):
    def cmd(self):
        return O.podman_cmd('n', 'img:tag', '/home/u', 'jobs/n', 'proj/n', 'skill/abc', 4, 900)

    def test_container_is_isolated_and_mounts_are_read_only_where_they_should_be(self):
        c = self.cmd(); j = ' '.join(c)
        for need in ('--network none', '--read-only', '--cap-drop ALL', 'no-new-privileges', '--memory 4g', '--memory-swap 4g', '--timeout 900'):
            self.assertIn(need, j)
        mounts = [c[i + 1] for i, x in enumerate(c) if x == '-v']
        self.assertEqual(sorted(m.rsplit(':', 2)[-2] for m in mounts), ['/godot', '/job', '/project', '/skills'])
        self.assertTrue(any(m.endswith('/godot:ro,z') for m in mounts) and any(m.endswith('/skills:ro,z') for m in mounts))
        self.assertTrue(any(m.endswith('/project:z') for m in mounts) and any(m.endswith('/job:z') for m in mounts))
        self.assertNotIn('--device', j)
        self.assertIn('LIBGL_ALWAYS_SOFTWARE=1', j)
        self.assertEqual(c[-3:], ['python3', '/job/godot_game_driver.py', '840'])

    def test_from_project_keeps_gg_data_continuity_except_scratch_subdirs(self):
        # a chained from_project job must still see an earlier job's adopted results (style.resolved.json,
        # world/, census.json, scatter/), so only the scratch/job-history subdirs may be excluded wholesale.
        self.assertEqual(O.SKIP_FROM_PROJECT_GG_DATA, ['--exclude=/gg_data/jobs/', '--exclude=/gg_data/export/stage/', '--exclude=/gg_data/selftest*/'])
        source = pathlib.Path(O.__file__).read_text()
        self.assertNotIn("'--exclude=/gg_data/'", source)

    def test_large_files_skipped_by_the_copy_are_listed_for_the_rig(self):
        # T-0134: main.tscn needs a 245 MB hero.glb; the copy drops files over COPY_MAX_MB, so they go to Bazzite directly.
        with tempfile.TemporaryDirectory() as d, mock.patch.object(O.godot_game_spec, 'COPY_MAX_MB', 1):
            root = pathlib.Path(d)
            for name, size in (('assets/hero.glb', 3), ('assets/a b.glb', 2), ('small.gd', 0), ('.godot/imported/x.scn', 3), ('.opencode/tmp/big', 3), ('gg_data/jobs/j/big', 3)):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_bytes(b'x' * (size * 1024 * 1024 + (1 if size else 10)))
            self.assertEqual(O.large_files(root), ['assets/a b.glb', 'assets/hero.glb'])
            send, skipped = O.plan_large(root, O.large_files(root), 3 * 1024 * 1024)
            self.assertEqual(([x['path'] for x in send], skipped), (['assets/a b.glb'], ['assets/hero.glb']))
            self.assertRegex(send[0]['sha256'], '^[0-9a-f]{64}$')

    def test_failure_reason_priority(self):
        d = {'selftest': {'exit': 0}, 'steps': [{'i': 1, 'script': 'gg_player.py', 'sub': 'smoke', 'exit': 1}], 'failed_at': 1, 'timed_out': False}
        self.assertIn('timeout', O.failure_reason(None, d, True))
        self.assertIn('no driver.json', O.failure_reason(1, None, True))
        self.assertIn('deadline', O.failure_reason(1, dict(d, timed_out=True), True))
        self.assertIn('selftest failed', O.failure_reason(1, dict(d, selftest={'exit': 4}, failed_at=0), True))
        self.assertIn('step 1 (gg_player.py smoke) exited 1', O.failure_reason(1, d, True))
        self.assertIn('logs/01-gg_player-smoke.log', O.failure_reason(1, d, True))
        self.assertIn('logs/00-selftest.log', O.failure_reason(1, dict(d, selftest={'exit': 4}, failed_at=0), True))
        self.assertIn('copied back', O.failure_reason(0, dict(d, failed_at=None), False))

    def test_tree_hash_changes_with_content_and_refuses_links(self):
        with tempfile.TemporaryDirectory() as t:
            r = pathlib.Path(t); (r / 'a').write_text('1')
            h = O.tree_hash(r); self.assertEqual(h, O.tree_hash(r))
            (r / 'a').write_text('2'); self.assertNotEqual(h, O.tree_hash(r))
            (r / 'l').symlink_to(r / 'a')
            with self.assertRaises(ValueError): O.tree_hash(r)


class ProjectGate(unittest.TestCase):
    def test_a_project_without_project_godot_is_accepted(self):
        """A godot-game job works on its own scratch copy, so the live project need not be a Godot project (heroquest-quest1-poc is not)."""
        src = pathlib.Path(O.__file__).read_text()
        gate = src[src.index("if not a.i_approve"):src.index("a.evidence.mkdir")]
        self.assertNotIn("project.godot", gate)
        self.assertIn("/data/ai/projects/games", gate)


class Driver(unittest.TestCase):
    """Runs the real driver against a fake skill whose scripts only record their argv, so the order, --project injection and stop-at-first-failure are proven."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = pathlib.Path(self.tmp.name)
        self.skill, self.job, self.project = t / 'skill', t / 'job', t / 'project'
        for d in (self.skill / 'scripts', self.job, self.project): d.mkdir(parents=True)
        rec = 'import sys,json,os;open(os.environ["GG_JOB_DIR"]+"/calls.jsonl","a").write(json.dumps(sys.argv[1:])+"\\n");sys.exit(int(os.environ.get("FAKE_EXIT_"+os.path.basename(sys.argv[0])[:-3],"0")))\n'
        for n in ('gg_verify', 'gg_project', 'gg_terrain', 'gg_player'): (self.skill / 'scripts' / (n + '.py')).write_text(rec)

    def tearDown(self):
        self.tmp.cleanup()

    def run_driver(self, steps, **env):
        (self.job / 'steps.json').write_text(json.dumps(steps))
        e = dict(os.environ, GG_JOB_DIR=str(self.job), GG_SKILL_DIR=str(self.skill), GG_PROJECT_DIR=str(self.project), **env)
        r = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve().parent / 'godot_game_driver.py'), '60'], env=e, capture_output=True, text=True)
        calls = [json.loads(x) for x in (self.job / 'calls.jsonl').read_text().splitlines()] if (self.job / 'calls.jsonl').exists() else []
        return r.returncode, json.loads((self.job / 'driver.json').read_text()), calls

    def test_selftest_first_then_steps_with_project(self):
        code, rep, calls = self.run_driver([{'script': 'gg_terrain.py', 'sub': 'build', 'args': ['--x', '1']}, {'script': 'gg_player.py', 'sub': 'smoke', 'args': []}])
        self.assertEqual(code, 0)
        self.assertEqual(calls[0][0], 'selftest'); self.assertIn('gl_compatibility', calls[0])
        self.assertEqual(calls[1], ['build', '--project', str(self.project), '--x', '1'])
        self.assertEqual(calls[2], ['smoke', '--project', str(self.project)])
        self.assertEqual([s['exit'] for s in rep['steps']], [0, 0]); self.assertIsNone(rep['failed_at'])

    def test_stops_at_first_failing_step(self):
        code, rep, calls = self.run_driver([{'script': 'gg_terrain.py', 'sub': 'build', 'args': []}, {'script': 'gg_player.py', 'sub': 'smoke', 'args': []}], FAKE_EXIT_gg_terrain='1')
        self.assertEqual(code, 1); self.assertEqual(rep['failed_at'], 1); self.assertEqual(len(rep['steps']), 1); self.assertEqual(len(calls), 2)

    def test_failed_selftest_runs_no_step(self):
        code, rep, calls = self.run_driver([{'script': 'gg_terrain.py', 'sub': 'build', 'args': []}], FAKE_EXIT_gg_verify='4')
        self.assertEqual(code, 1); self.assertEqual(rep['steps'], []); self.assertEqual(rep['failed_at'], 0); self.assertEqual(len(calls), 1)

    def test_doctor_gets_no_project_flag(self):
        code, rep, calls = self.run_driver([{'script': 'gg_project.py', 'sub': 'doctor', 'args': []}])
        self.assertEqual(calls[1], ['doctor'])


if __name__ == '__main__':
    unittest.main()
