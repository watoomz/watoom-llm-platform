"""Every operator-side worker script must at least compile: a SyntaxError in one only shows up as 'Helper did not produce result' for the model."""
import pathlib, py_compile, tempfile, unittest

HERE = pathlib.Path(__file__).parent
PATTERNS = ('game_*.py', '*_spec.py', 'godot_game_driver.py', 'asset_capture*.py', 'blender_*.py', 'capture_*.py', 'project_captures.py', 'repair_game_request.py')


class Compile(unittest.TestCase):
    def test_all_operator_scripts_compile(self):
        files = sorted({f for pat in PATTERNS for f in HERE.glob(pat) if not f.name.startswith('test_')})
        self.assertGreater(len(files), 15)
        with tempfile.TemporaryDirectory() as tmp:
            for f in files:
                with self.subTest(file=f.name):
                    py_compile.compile(str(f), cfile=str(pathlib.Path(tmp) / (f.name + 'c')), doraise=True)


if __name__ == '__main__':
    unittest.main()
