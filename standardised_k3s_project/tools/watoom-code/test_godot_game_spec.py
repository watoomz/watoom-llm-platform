import json, pathlib, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import godot_game_spec as G


class Spec(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = pathlib.Path(self.tmp.name) / 'proj'
        self.stage = self.project / '.opencode/tmp/game'
        self.stage.mkdir(parents=True)
        (self.project / '.opencode/godot-game-jobs/j1').mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def existing_project(self, preset='low-poly'):
        (self.stage / 'project.godot').write_text('x')
        (self.stage / 'gg_project.json').write_text(json.dumps({'style': {'preset': preset}}))

    def write(self, **kw):
        v = {'schema': 1, 'project_dir': '.opencode/tmp/game', 'steps': [{'script': 'gg_player.py', 'sub': 'smoke', 'args': []}]}
        v.update(kw)
        v = {k: x for k, x in v.items() if x is not None}
        (self.project / '.opencode/godot-game-jobs/j1/request.json').write_text(json.dumps(v))

    def load(self, **kw):
        self.write(**kw)
        return G.load(self.project, 'j1')

    def test_valid_existing_project(self):
        self.existing_project()
        r = self.load(steps=[{'script': 'gg_player.py', 'sub': 'build'}, {'script': 'gg_player.py', 'sub': 'smoke', 'args': ['--walk-s', '3']}])
        self.assertEqual((r['deadline_sec'], r['memory_gib'], len(r['steps'])), (900, 4, 2))
        self.assertEqual(r['steps'][0]['args'], [])

    def test_init_needs_empty_dir_and_gl_style(self):
        init = lambda *a: [{'script': 'gg_project.py', 'sub': 'init', 'args': ['--name', 'g', '--style', *a]}]
        self.assertEqual(self.load(steps=init('low-poly'))['steps'][0]['sub'], 'init')
        self.assertEqual(self.load(steps=[{'script': 'gg_project.py', 'sub': 'init', 'args': ['--style=pixel-art']}])['steps'][0]['args'], ['--style=pixel-art'])
        with self.assertRaisesRegex(ValueError, 'needs --style low-poly or pixel-art'): self.load(steps=init('realistic'))
        with self.assertRaisesRegex(ValueError, 'needs --style'): self.load(steps=[{'script': 'gg_project.py', 'sub': 'init', 'args': []}])
        (self.stage / 'x').write_text('x')
        with self.assertRaisesRegex(ValueError, 'must be empty'): self.load(steps=init('low-poly'))

    def test_vulkan_project_refused(self):
        self.existing_project('realistic')
        with self.assertRaisesRegex(ValueError, 'needs a GPU'): self.load()

    def test_project_files_required_without_init(self):
        with self.assertRaisesRegex(ValueError, 'needs a regular project.godot'): self.load()

    def test_project_dir_must_be_scratch(self):
        self.existing_project()
        for bad in ('.', 'levels', '.opencode/tmp/../x', '/etc', '.opencode/tmp/nope'):
            with self.assertRaises(ValueError, msg=bad): self.load(project_dir=bad)

    def test_steps_typed(self):
        self.existing_project()
        for bad in ({'script': 'bash', 'sub': 'x'}, {'script': 'gg_style.py', 'sub': 'calibrate'}, {'script': 'gg_verify.py', 'sub': 'shot'}, {'script': 'gg_player.py', 'sub': 'smoke', 'extra': 1},
                    {'script': 'gg_player.py', 'sub': 'smoke', 'args': ['--out', '/tmp/x']}, {'script': 'gg_player.py', 'sub': 'smoke', 'args': ['/etc/passwd']}, {'script': 'gg_player.py', 'sub': 'smoke', 'args': ['--project=x']},
                    {'script': 'gg_player.py', 'sub': 'smoke', 'args': ['--project x']}, {'script': 'gg_player.py', 'sub': 'smoke', 'args': ['a$(x)']}, {'script': 'gg_player.py', 'sub': 'smoke', 'args': ['a;b']},
                    {'script': 'gg_player.py', 'sub': 'smoke', 'args': ['`x`']}, {'script': 'gg_player.py', 'sub': 'smoke', 'args': [1]}, {'script': 'gg_player.py', 'sub': 'smoke', 'args': ['x'] * 25}):
            with self.assertRaises(ValueError, msg=bad): self.load(steps=[bad])

    def test_waypoints_value_with_spaces_and_commas_allowed(self):
        self.existing_project()
        r = self.load(steps=[{'script': 'gg_water.py', 'sub': 'creek', 'args': ['--waypoints', '20,30 60,80 120,200']}])
        self.assertEqual(r['steps'][0]['args'][1], '20,30 60,80 120,200')

    def test_limits(self):
        self.existing_project()
        with self.assertRaises(ValueError): self.load(steps=[])
        with self.assertRaises(ValueError): self.load(steps=[{'script': 'gg_player.py', 'sub': 'status'}] * 13)
        for kw in ({'deadline_sec': 60}, {'deadline_sec': 1801}, {'deadline_sec': True}, {'memory_gib': 2}, {'memory_gib': 9}, {'memory_gib': 'x'}, {'schema': 2}, {'unknown': 1}):
            with self.assertRaises(ValueError, msg=kw): self.load(**kw)

    def test_request_must_be_regular_file_and_small(self):
        self.existing_project()
        f = self.project / '.opencode/godot-game-jobs/j1/request.json'
        self.write()
        f.unlink(); (self.project / 'real.json').write_text('{}'); f.symlink_to(self.project / 'real.json')
        with self.assertRaisesRegex(ValueError, 'regular file'): G.load(self.project, 'j1')
        f.unlink(); f.write_text(' ' * 20000)
        with self.assertRaisesRegex(ValueError, '16 KiB'): G.load(self.project, 'j1')
        with self.assertRaises(ValueError): G.path(self.project, '../x')

    def test_symlinked_project_dir_refused(self):
        self.existing_project()
        real = self.project / 'elsewhere'; real.mkdir()
        (self.project / '.opencode/tmp/link').symlink_to(real)
        with self.assertRaises(ValueError): self.load(project_dir='.opencode/tmp/link')

    def test_revision_follows_manifest_bytes_only(self):
        self.existing_project()
        self.write(); a = G.revision(self.project, 'j1')
        (self.stage / 'gg_project.json').write_text(json.dumps({'style': {'preset': 'pixel-art'}}))
        self.assertEqual(a, G.revision(self.project, 'j1'))
        self.write(deadline_sec=600)
        self.assertNotEqual(a, G.revision(self.project, 'j1'))

    @unittest.skipUnless(__import__('shutil').which('node'), 'node not available')
    def test_python_and_guard_fingerprints_agree(self):
        import subprocess
        self.existing_project(); self.write()
        guard = pathlib.Path(__file__).resolve().parents[2] / 'ansible/roles/watoom-code/files/coordinator-guard/index.js'
        js = subprocess.run(['node', '--input-type=module', '-e', "import {godotGameSpecFingerprint as f} from %s;console.log(await f(%s,'j1'))" % (json.dumps(str(guard)), json.dumps(str(self.project.resolve())))],
                            capture_output=True, text=True, timeout=60)
        self.assertEqual(js.stdout.strip(), G.revision(self.project.resolve(), 'j1'), js.stderr[-300:])

    def test_every_allowed_script_exists_in_the_skill(self):
        for script, subs in G.STEPS.items():
            self.assertTrue((G.SKILL / 'scripts' / script).is_file(), script)
            text = (G.SKILL / 'scripts' / script).read_text()
            for sub in subs: self.assertIn(sub, text, script + ' ' + sub)

    def test_ui_steps_and_res_paths(self):
        self.stage.joinpath('project.godot').write_text('x'); self.stage.joinpath('gg_ui.json').write_text('{}')
        steps = [{'script': 'gg_ui.py', 'sub': 'test'}, {'script': 'gg_ui.py', 'sub': 'shot', 'args': ['--scene', 'res://scenes/main.tscn', '--size', '1920x240', '--dock', 'bottom']},
                 {'script': 'gg_ui.py', 'sub': 'overlay-check', 'args': ['--scene=res://scenes/main.tscn']} ][:2]
        self.assertEqual(len(self.load(steps=steps)['steps']), 2)
        for bad in (['--scene', 'res://../x.tscn'], ['--scene', '/etc/passwd'], ['--name', 'res://scenes/main.tscn'], ['--scene', 'res://a;b.tscn'], ['--scene', 'user://x.tscn'], ['--out', 'x']):
            with self.assertRaises(ValueError): self.load(steps=[{'script': 'gg_ui.py', 'sub': 'shot', 'args': bad}])
        self.assertEqual(self.load(steps=[{'script': 'gg_assets.py', 'sub': 'check', 'args': ['--slot', 'hero']}])['steps'][0]['sub'], 'check')
        for sub in ('use', 'find'):
            with self.assertRaisesRegex(ValueError, 'not allowed for gg_assets.py'): self.load(steps=[{'script': 'gg_assets.py', 'sub': sub, 'args': ['--slot', 'hero']}])
        with self.assertRaisesRegex(ValueError, 'not allowed for gg_ui.py'): self.load(steps=[{'script': 'gg_ui.py', 'sub': 'frobnicate'}])
        with self.assertRaises(ValueError): self.load(steps=[{'script': 'gg_player.py', 'sub': 'smoke', 'args': ['--scene', 'res://scenes/main.tscn']}])

    def test_operator_scripts_compile(self):
        import py_compile
        for f in ('game_godot_game.py', 'godot_game_driver.py', 'godot_game_spec.py'):
            py_compile.compile(str(pathlib.Path(__file__).with_name(f)), doraise=True)

    def test_init_may_name_a_folder_that_does_not_exist_yet(self):
        init = [{'script': 'gg_ui.py', 'sub': 'init', 'args': ['--name', 'strip']}]
        import shutil; shutil.rmtree(self.stage); shutil.rmtree(self.stage.parent) if self.stage.parent.name == 'tmp' else None
        r = self.load(steps=init)
        self.assertTrue(r['create_directory'])
        with self.assertRaisesRegex(ValueError, 'does not exist'): self.load(steps=[{'script': 'gg_ui.py', 'sub': 'test'}])
        self.assertFalse(self.load(steps=[{'script': 'gg_ui.py', 'sub': 'init', 'args': ['--name', 'strip']}]) is None)

    def test_from_project_copies_the_live_project(self):
        import shutil; shutil.rmtree(self.stage)
        (self.project / 'gg_ui.json').write_text('{}'); (self.project / 'project.godot').write_text('x')
        r = self.load(from_project=True, steps=[{'script': 'gg_ui.py', 'sub': 'test'}])
        self.assertTrue(r['from_project'] and r['create_directory'])
        with self.assertRaisesRegex(ValueError, 'cannot be an init step'): self.load(from_project=True, steps=[{'script': 'gg_ui.py', 'sub': 'init', 'args': ['--name', 'x']}])
        with self.assertRaisesRegex(ValueError, 'from_project must be'): self.load(from_project='yes', steps=[{'script': 'gg_ui.py', 'sub': 'test'}])
        self.stage.mkdir(parents=True); (self.stage / 'old').write_text('x')
        with self.assertRaisesRegex(ValueError, 'must not exist yet or be empty'): self.load(from_project=True, steps=[{'script': 'gg_ui.py', 'sub': 'test'}])
        self.assertTrue(G.revision(self.project, 'j1'))  # the fingerprint is read again after the run, with the staging folder full
        (self.project / 'project.godot').unlink(); (self.stage / 'old').unlink()
        with self.assertRaisesRegex(ValueError, 'project.godot'): self.load(from_project=True, steps=[{'script': 'gg_ui.py', 'sub': 'test'}])

    def test_ui_init_needs_an_empty_dir_and_a_ui_project_needs_its_files(self):
        init = [{'script': 'gg_ui.py', 'sub': 'init', 'args': ['--name', 'strip', '--height', '240']}]
        self.assertEqual(self.load(steps=init)['steps'][0]['script'], 'gg_ui.py')
        (self.stage / 'x').write_text('x')
        with self.assertRaisesRegex(ValueError, 'must be empty when the first step is gg_ui.py init'): self.load(steps=init)
        # after the job ran the folder is full: re-reading the request for its fingerprint must still work (it turned PASS into RECONCILIATION_REQUIRED)
        self.assertEqual(G.revision(self.project, 'j1'), G.revision(self.project, 'j1'))
        (self.stage / 'x').unlink(); self.stage.joinpath('gg_ui.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'needs a regular project.godot and gg_ui.json'): self.load(steps=[{'script': 'gg_ui.py', 'sub': 'test'}])


class AuditFixes(Spec):
    def test_post_run_reread_ignores_live_project_state(self):
        self.write(); self.existing_project()
        self.assertTrue(G.revision(self.project, 'j1'))
        (self.stage / 'gg_project.json').write_text('{"style": {"preset": "realistic"}}')
        self.assertTrue(G.revision(self.project, 'j1'))   # the model changed the style while the job ran: still just a fingerprint

    def test_bad_gg_project_json_is_a_value_error_not_a_crash(self):
        for body in ('{"style": null}', '[1]', 'nope'):
            self.existing_project()
            (self.stage / 'gg_project.json').write_text(body)
            with self.assertRaises(ValueError, msg=body): self.load()

    def test_abbreviated_forbidden_flags_and_error_index(self):
        for bad in ('--ou x', '--pro x', '--o', '--wor=1'):
            with self.assertRaisesRegex(ValueError, 'set by the worker', msg=bad): G.check_step(0, {'script': 'gg_project.py', 'sub': 'show', 'args': [bad]})
        with self.assertRaisesRegex(ValueError, r'steps\[2\]\.args'): G.check_step(2, {'script': 'gg_project.py', 'sub': 'show', 'args': ['ok', 'ok', 'ok', 'a/b']})
        self.assertEqual(G.check_step(0, {'script': 'gg_ui.py', 'sub': 'shot', 'args': ['--scene=res://scenes/main.tscn']})['args'], ['--scene=res://scenes/main.tscn'])


if __name__ == '__main__':
    unittest.main()