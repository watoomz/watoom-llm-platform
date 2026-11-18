import ast,json,pathlib,unittest
import three_d
ROOT=pathlib.Path(__file__).resolve().parent
class LocalOnly(unittest.TestCase):
 def test_registry(self):
  rows=three_d.registry()
  self.assertNotIn('meshy',[row['id'] for row in rows])
  self.assertTrue(all(row['backend'] in ('blender-cpu','generic-specialist') for row in rows))
  self.assertIn('asset-assistant.avian',[row['id'] for row in rows])
 def test_no_active_routes_imports_or_image(self):
  source=(ROOT/'agent.py').read_text();ast.parse(source)
  self.assertNotIn('meshy',source.lower())
  self.assertNotIn('meshy',(ROOT/'Containerfile.3d').read_text().lower())
  self.assertNotIn('meshy.py',[entry['path'] for entry in json.loads((ROOT/'3d-source.json').read_text())['files']])
if __name__=='__main__':unittest.main()
