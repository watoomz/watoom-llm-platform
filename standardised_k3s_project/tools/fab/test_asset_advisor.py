"""Offline regression tests; fixtures preserve real catalogue titles and format labels.

Run: python3 -B -m unittest discover -s tools/fab -p test_asset_advisor.py -v
No test downloads, launches engines, or writes an index.
"""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

SKILL_SCRIPTS = Path(__file__).resolve().parents[2] / 'ansible/roles/watoom-code/files/skills/watoom-fab-owned-assets/scripts'
sys.path.insert(0, str(SKILL_SCRIPTS))  # the advisor ships inside the skill so agents can run it from /config/skills
import asset_advisor as advisor


DOG = {'id': '069c43002d2b407282a64f028fb174d3',
       'title': 'German Shepherd 3D Dog Model', 'type': 'ASSET_PACK', 'source': 'ue-library'}
MEGAPLANT = {'id': 'plant', 'title': 'Megaplants: European Hornbeam',
            'type': 'ASSET_PACK', 'source': 'ue-library'}
MEGASCANS = {'id': '92b0303b359d477e9b6f023adf8a8293',
            'title': 'Medieval Village Megascans Sample',
            'type': 'COMPLETE_PROJECT', 'source': 'ue-library'}
GODOT = {'id': '1790', 'title': 'POLY - Nature', 'source': 'animpic',
         'formats': ['Blender', 'Godot', 'Unity', 'Unreal']}
HEIGHTMAP = {'id': '398293c94e3940a2aae09f0202b7ef7b',
             'title': '20 Heightmaps 4K and Auto-landscape materials',
             'type': 'ASSET_PACK', 'source': 'ue-library'}


class AssetAdvisorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.taxonomy = advisor.load_taxonomy()

    def classify(self, item, facts=None):
        return advisor.classify(item, facts, self.taxonomy)

    def test_real_dog_candidate_does_not_invent_rig_facts(self):
        dog = self.classify(DOG)
        self.assertEqual(dog['category'], 'animals')
        self.assertEqual(dog['pipeline_ids'], ['unreal-skeletal-to-godot'])
        self.assertIsNone(dog['rigged'])
        self.assertIsNone(dog['animated'])
        self.assertEqual(dog['formats'], [])
        self.assertLess(dog['confidence'], 1)
        self.assertTrue(dog['requires_owner_approval'])
        self.assertNotIn('category', DOG)  # Input stays untouched.

    def test_megascans_content_and_complete_project_boundary(self):
        sample = self.classify(MEGASCANS)
        self.assertEqual(sample['category'], 'megascans')
        self.assertEqual(sample['pipeline_ids'], ['no-godot-project'])
        plant = self.classify(MEGAPLANT)
        self.assertEqual(plant['category'], 'megascans')
        self.assertEqual(plant['pipeline_ids'], ['megascans-static'])

    def test_native_godot_format_precedes_conversion(self):
        asset = self.classify(GODOT)
        self.assertEqual(asset['category'], 'environment')
        self.assertEqual(asset['pipeline_ids'], ['native-godot'])
        self.assertFalse(asset['requires_owner_approval'])
        advice = advisor.advise('1790', [asset], self.taxonomy)['matches'][0]
        self.assertFalse(advice['pipelines'][0]['requires_owner_approval'])
        self.assertIn('no conversion', ' '.join(advice['pipelines'][0]['steps']))

    def test_heightmaps_precede_material_keywords(self):
        asset = self.classify(HEIGHTMAP)
        self.assertEqual(asset['category'], 'terrain')
        self.assertEqual(asset['pipeline_ids'], ['terrain-real-place', 'terrain-unreal-bake'])

    def test_facts_category_tags_formats_override_guesses(self):
        asset = self.classify(DOG, {'category': 'materials', 'formats': ['Godot']})
        self.assertEqual(asset['category'], 'materials')
        self.assertEqual(asset['confidence'], 1.0)
        self.assertEqual(asset['pipeline_ids'], ['native-godot'])
        self.assertTrue(any('facts listing category' in x for x in asset['evidence']))
        tagged = self.classify(DOG, {'tags': ['audio', 'sound'], 'formats': ['WAV']})
        self.assertEqual(tagged['category'], 'audio')
        self.assertEqual(tagged['formats'], ['WAV'])
        self.assertEqual(tagged['pipeline_ids'], ['audio-import'])
        unknown = self.classify(DOG, {'category': 'Unrecognised listing label'})
        self.assertEqual(unknown['category'], 'uncategorised')

    def test_scanned_unrigged_dog_uses_rigify(self):
        asset = self.classify(DOG, {'has_skeletal_mesh': False, 'has_static_mesh': True,
                                    'anim_count': 0})
        self.assertEqual(asset['category'], 'animals')
        self.assertEqual(asset['pipeline_ids'], ['rigify-static-character'])
        self.assertFalse(asset['rigged'])
        self.assertFalse(asset['animated'])
        advice = advisor.advise(asset['id'], [asset], self.taxonomy)['matches'][0]
        steps = ' '.join(advice['pipelines'][0]['steps'])
        for required in ('--add auto --auto-fit', '--generate', 'auto_fit.quality',
                         'Weld split-vertex', 'bind_mesh.py', '--target-armature'):
            self.assertIn(required, steps)

    def test_scanned_skeleton_resolves_unknown_and_preserves_known_animal(self):
        mystery = {'id': 'unknown', 'title': 'Whisper', 'source': 'ue-library'}
        self.assertEqual(self.classify(mystery)['category'], 'uncategorised')
        self.assertEqual(self.classify(mystery, {'has_skeletal_mesh': True})['category'],
                         'characters')
        self.assertEqual(self.classify(DOG, {'has_skeletal_mesh': True})['category'], 'animals')
        clips = self.classify(DOG, {'has_mesh': False, 'anim_count': 12})
        self.assertEqual(clips['category'], 'animations')
        self.assertEqual(clips['pipeline_ids'], ['retarget-animation'])

    def test_animations_and_portable_character(self):
        clips = self.classify(dict(DOG, title='Free Animation Library'))
        self.assertEqual(clips['pipeline_ids'], ['retarget-animation'])
        portable = self.classify(DOG, {'formats': ['FBX'], 'rigged': True})
        self.assertEqual(portable['pipeline_ids'], ['portable-character'])
        static = self.classify(dict(DOG, title='AI Generated Animal Robots - Static Models'))
        self.assertEqual(static['pipeline_ids'], ['rigify-static-character'])

    def test_blocked_native_types_cannot_be_unblocked_by_content_facts(self):
        for kind, pipeline in [('CODE_PLUGIN', 'no-godot-plugin'),
                               ('COMPLETE_PROJECT', 'no-godot-project'),
                               ('METAHUMAN', 'metahuman-pipeline')]:
            asset = self.classify(dict(DOG, type=kind), {'category': 'animals'})
            self.assertEqual(asset['pipeline_ids'], [pipeline])
        bridge = self.classify(dict(DOG, title='Quixel Bridge', type='CODE_PLUGIN'))
        self.assertEqual(bridge['category'], 'code_plugins')

    def test_advise_shape_ranking_filter_and_missing_query(self):
        assets = [self.classify(x) for x in (DOG, GODOT, HEIGHTMAP)]
        result = advisor.advise(DOG['id'], assets, self.taxonomy)
        self.assertEqual(result['total_matches'], 1)
        match = result['matches'][0]
        for key in ('category', 'source', 'formats', 'confidence', 'evidence',
                    'pipelines', 'approval_reminder'):
            self.assertIn(key, match)
        self.assertIn('explicit per-asset owner approval', match['approval_reminder'])
        for key in ('id', 'applies_to', 'steps', 'tools', 'pitfalls', 'status',
                    'requires_owner_approval', 'qualification_scope'):
            self.assertIn(key, match['pipelines'][0])
        self.assertEqual(advisor.advise('Shepherd', assets, self.taxonomy,
                                        category='terrain')['matches'], [])
        self.assertEqual(advisor.advise('no-such-asset', assets, self.taxonomy)['matches'], [])
        self.assertEqual(advisor.advise('', assets, self.taxonomy)['matches'], [])
        self.assertEqual(advisor.advise('fab:' + DOG['id'], assets,
                                        self.taxonomy)['matches'][0]['id'], DOG['id'])

    def test_all_pipeline_definitions_have_real_skill_provenance(self):
        root = Path(__file__).resolve().parents[2]
        ids = set()
        for pipeline in self.taxonomy['pipelines']:
            self.assertNotIn(pipeline['id'], ids)
            ids.add(pipeline['id'])
            self.assertIn(pipeline['status'], ('QUALIFIED', 'CANDIDATE'))
            self.assertIsInstance(pipeline['requires_owner_approval'], bool)
            for key in ('applies_to', 'steps', 'tools', 'pitfalls', 'skill_sources'):
                self.assertTrue(pipeline[key], (pipeline['id'], key))
            for source in pipeline['skill_sources']:
                self.assertTrue((root / source).is_file(), source)

    def test_facts_file_and_cli_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for name, items in [('fab', [DOG]), ('animpic', [GODOT])]:
                (folder / (name + '-owned.json')).write_text(json.dumps({'assets': items}))
            facts = {'fab:' + DOG['id']: {'has_skeletal_mesh': False},
                     GODOT['id']: {'category': 'environment'}}
            path = folder / 'facts.json'
            path.write_text(json.dumps(facts))
            assets, inventories = advisor.load_assets(folder, facts, self.taxonomy)
            self.assertEqual(assets[0]['pipeline_ids'], ['rigify-static-character'])
            self.assertEqual(inventories['fab']['count'], 1)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(advisor.main(['advise', DOG['id'], '--catalog-dir', str(folder),
                                               '--facts', str(path), '--json']), 0)
            self.assertEqual(json.loads(output.getvalue())['matches'][0]['category'], 'animals')
            # build writes only to the requested directory (the real catalogue is the default, never touched here)
            out = folder / 'out'
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(advisor.main(['build', '--catalog-dir', str(folder), '--facts', str(path),
                                               '--output-dir', str(out)]), 0)
            index = json.loads((out / 'asset-index.json').read_text())
            self.assertEqual(index['assets'][0]['id'], DOG['id'])
            self.assertTrue((out / 'asset-index.md').is_file())
            self.assertEqual(advisor.OUTPUT, advisor.CATALOG)
            # a fab-listing-facts.json beside the catalogues applies without --facts
            (folder / 'fab-listing-facts.json').write_text(json.dumps({DOG['id']: {'category': 'creatures'}}))
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                self.assertEqual(advisor.main(['advise', DOG['id'], '--catalog-dir', str(folder), '--json']), 0)
            self.assertEqual(json.loads(buffer.getvalue())['matches'][0]['category'], 'creatures')


if __name__ == '__main__':
    unittest.main()
