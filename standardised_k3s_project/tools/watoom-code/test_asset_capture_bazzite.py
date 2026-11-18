import pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import asset_capture_bazzite as acb

class Dependencies(unittest.TestCase):
    def test_absolute_strings_walks_nested_manifest(self):
        v={'source':'/a/b.blend','preparation':{'plan':{'clip':'/c/d.clip','n':3,'x':['/e/f.png','rel/x']}}}
        self.assertEqual({'/a/b.blend','/c/d.clip','/e/f.png'},set(acb.absolute_strings(v)))
    def test_dependencies_keeps_only_files_under_roots_outside_the_source_folder(self):
        with tempfile.TemporaryDirectory() as t:
            t=pathlib.Path(t).resolve();(t/'asset').mkdir();(t/'shared').mkdir();(t/'other').mkdir()
            src=t/'asset/m.glb';src.write_bytes(b'x');tex=t/'shared/t.png';tex.write_bytes(b'y');out=t/'other/z.clip';out.write_bytes(b'z');inside=t/'asset/i.png';inside.write_bytes(b'i')
            v={'source':str(src),'a':str(tex),'b':str(out),'c':str(inside),'d':str(t/'shared/missing.png')}
            got=acb.dependencies(v,[str(t/'asset'),str(t/'shared')])
            self.assertEqual([tex],got)
    def test_tree_size_ignores_links(self):
        with tempfile.TemporaryDirectory() as t:
            t=pathlib.Path(t);(t/'a').write_bytes(b'12345');(t/'l').symlink_to(t/'a')
            self.assertEqual((5,1),acb.tree_size(t))
if __name__=='__main__':unittest.main()
