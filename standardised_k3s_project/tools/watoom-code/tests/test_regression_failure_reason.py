import sys,pathlib,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from game_validation import regression_failure_reason as reason
class Reason(unittest.TestCase):
 def test_missing_summary_line_is_named(self):
  self.assertIn('passed=N failed=N total=N',reason(None,0))
 def test_failed_inconsistent_and_runtime_errors(self):
  self.assertEqual(reason((12,1,13),0),'1 of 13 tests failed')
  self.assertIn('inconsistent',reason((0,0,0),0))
  self.assertIn('2 runtime',reason((13,0,13),2))
 def test_clean_pass_has_no_reason(self):
  self.assertIsNone(reason((13,0,13),0))
if __name__=='__main__':unittest.main()


class GodotErrors(unittest.TestCase):
    def test_shader_cause_and_location_are_kept(self):
        from game_validation import godot_errors
        log = ("--res://scripts/shaders/dirt_soil.gdshader--\nE  39->  world_pos = WORLD_POSITION;\n"
               "SHADER ERROR: Unknown identifier in expression: 'WORLD_POSITION'.\n          at: (null) (res://scripts/shaders/dirt_soil.gdshader:39)\n"
               "ERROR: Shader compilation failed.\nERROR: Shader compilation failed.\nWARNING: ignored\n")
        errors = godot_errors(log)
        self.assertEqual(len(errors), 2, 'distinct only')
        self.assertIn('WORLD_POSITION', errors[0]);self.assertIn('dirt_soil.gdshader:39', errors[0])

    def test_import_reason_names_the_cause(self):
        from game_validation import import_failure_reason
        self.assertIn('source_changes_by_import', import_failure_reason([], {'created': ['a.uid']}, True, True))
        self.assertIn('changed while the import ran', import_failure_reason([], None, False, False))
        self.assertIn('2 Godot errors', import_failure_reason(['ERROR: a', 'ERROR: b'], None, True, False))
        self.assertIsNone(import_failure_reason([], None, True, True))

    def test_hints_match_known_causes_only(self):
        from game_validation import godot_hints
        self.assertIn('fbx_relink_to_glb', godot_hints(["ERROR: Can't open file from path 'res://../../Users/a/Color2.png'."])[0])
        self.assertIn('uid=', godot_hints(['ERROR: Unrecognized UID: "uid://abc".'])[0])
        self.assertEqual(godot_hints(['ERROR: Resource file not found: res://scenes/a.tscn (expected type: PackedScene)']), [])
