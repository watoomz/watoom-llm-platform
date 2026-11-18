"""Guards against a dedent slipping code out of a nested helper (regression: NameError 'reason' in game_bazzite.not_started)."""
import ast
import builtins
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WRAPPERS = ['game_bazzite.py', 'blender_bazzite.py', 'asset_capture_bazzite.py']


def undefined_names(path):
    tree = ast.parse(path.read_text())
    bound = set(dir(builtins)) | {'__file__'}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            bound.add(n.name)
        elif isinstance(n, ast.arg):
            bound.add(n.arg)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            bound.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                bound.add((a.asname or a.name).split('.')[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            bound.add(n.name)
    return sorted({n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in bound})


class WrapperStructureTests(unittest.TestCase):
    def test_no_undefined_names(self):
        for name in WRAPPERS:
            self.assertEqual([], undefined_names(ROOT / name), name)

    def test_reason_is_only_used_inside_not_started(self):
        tree = ast.parse((ROOT / 'game_bazzite.py').read_text())
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'not_started']:
            text = ast.unparse(fn)
            self.assertIn('NOT_STARTED', text)
            self.assertIn('failure_code', text)
            self.assertIn('SystemExit', text)


if __name__ == '__main__':
    unittest.main()
