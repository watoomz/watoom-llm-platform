import json, pathlib, sys, tempfile, unittest, zipfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import metahuman_pipeline as mp


def make_pack(root, editable=True, extra_member=None):
    pack = pathlib.Path(root) / 'fake-pack'
    pack.mkdir()
    manifest = {'name': 'MHC_X', 'assetData': {'objectPath': '/Game/EditableCharacters/X/MHC_X.MHC_X'},
                'dependentPackages': ['/Game/EditableCharacters/X/MHC_X', '/Game/EditableCharacters/X/X/T_X_Normal_Body'],
                'assetType': 'Character', 'details': {'bIsEditableCharacter': editable, 'includedLods': 0, 'numUniqueGrooms': 0, 'numUniqueClothingItems': 0}}
    with zipfile.ZipFile(pack / 'x.mhpkg', 'w') as z:
        z.writestr('MHC_X/Manifest.json', json.dumps(manifest))
        z.writestr('MHC_X/MHC_X.uasset', b'character')
        z.writestr('MHC_X/X/T_X_Normal_Body.uasset', b'texture')
        z.writestr('Manifest.json', json.dumps(manifest))
        if extra_member:
            z.writestr(extra_member, b'x')
    return pack, pack / 'x.mhpkg'


class Pipeline(unittest.TestCase):
    def test_inspect_classifies_editable_and_assembled(self):
        with tempfile.TemporaryDirectory() as t:
            pack, f = make_pack(t)
            self.assertEqual('editable', mp.inspect(pack, f)['characters'][0]['kind'])
        with tempfile.TemporaryDirectory() as t:
            pack, f = make_pack(t, editable=False)
            self.assertEqual('assembled', mp.inspect(pack, f)['characters'][0]['kind'])

    def test_unpack_maps_packages_under_game_to_content(self):
        with tempfile.TemporaryDirectory() as t:
            pack, f = make_pack(t)
            state = mp.unpack(pack, f)
            self.assertEqual('CONTENT_READY', state['engine_import'])
            self.assertEqual(b'character', (pack / 'Content/EditableCharacters/X/MHC_X.uasset').read_bytes())
            self.assertEqual(b'texture', (pack / 'Content/EditableCharacters/X/X/T_X_Normal_Body.uasset').read_bytes())
            with self.assertRaises(SystemExit):  # never rebuild silently
                mp.unpack(pack, f)

    def test_unsafe_members_are_refused(self):
        with tempfile.TemporaryDirectory() as t:
            pack, f = make_pack(t, extra_member='../evil.uasset')
            with self.assertRaises(SystemExit):
                mp.unpack(pack, f)
        with tempfile.TemporaryDirectory() as t:
            pack, f = make_pack(t, extra_member='MHC_X/run.sh')
            self.assertTrue(mp.inspect(pack, f)['unsafe_members'])

    def test_hash_mismatch_with_acquisition_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            pack, f = make_pack(t)
            (pack / 'acquisition.json').write_text(json.dumps({'sha256': '0' * 64}))
            with self.assertRaises(SystemExit):
                mp.unpack(pack, f)

    def test_copy_to_project_enables_plugins_and_never_overwrites_different_files(self):
        with tempfile.TemporaryDirectory() as t:
            pack, f = make_pack(t)
            mp.unpack(pack, f)
            project = pathlib.Path(t) / 'proj'
            (project / 'Content').mkdir(parents=True)
            (project / 'G.uproject').write_text(json.dumps({'FileVersion': 3, 'Plugins': [{'Name': 'RigLogic', 'Enabled': False}]}))
            out = mp.copy_to_project(pack, project)
            self.assertEqual(2, out['files'])
            plugins = {p['Name'] for p in json.loads((project / 'G.uproject').read_text())['Plugins']}
            self.assertTrue({'MetaHumanCharacter', 'MetaHumanSDK'} <= plugins)
            (project / 'Content/EditableCharacters/X/MHC_X.uasset').write_bytes(b'different')
            with self.assertRaises(SystemExit):
                mp.copy_to_project(pack, project)

    def test_normal_maps_get_green_inverted_and_downscaled(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            src = pathlib.Path(t) / 'n.png'
            Image.new('RGB', (64, 32), (10, 200, 30)).save(src)
            dst = pathlib.Path(t) / 'o.png'
            mp.tga_to_png(src, dst, 16, invert_green=True)
            with Image.open(dst) as im:
                self.assertEqual((16, 8), im.size)
                self.assertEqual((10, 55, 30), im.getpixel((0, 0)))


REAL_HEAD = [   # (index, verts, material, centre, size) read from the exported Base_Female head GLB
    (0, 124735, 0, [-0.0001, 1.5306, 0.0081], [0.3155, 0.374, 0.2207]), (1, 6066, 1, [0.0001, 1.5298, 0.0569], [0.0715, 0.0582, 0.0782]),
    (2, 660, 2, [-0.0001, 1.5363, 0.0717], [0.0699, 0.0229, 0.0483]), (3, 802, 3, [0.0365, 1.6127, 0.068], [0.0287, 0.0285, 0.0289]),
    (4, 802, 3, [-0.0365, 1.6129, 0.0677], [0.0292, 0.029, 0.0294]), (5, 560, 2, [-0.0002, 1.6103, 0.0782], [0.1033, 0.0119, 0.0123]),
    (6, 2144, 2, [-0.0004, 1.6106, 0.0815], [0.1199, 0.0227, 0.023]), (7, 276, 2, [-0.0001, 1.6101, 0.078], [0.1015, 0.0104, 0.0112]),
    (8, 386, 2, [-0.0001, 1.6106, 0.0775], [0.1077, 0.0155, 0.0142])]


def head_stats(rows=REAL_HEAD):
    return [{'index': i, 'verts': v, 'material': m, 'center': c, 'size': s} for i, v, m, c, s in rows]


class HeadSurfaces(unittest.TestCase):
    def test_roles_from_the_real_head_mesh(self):
        roles = {r['index']: r['role'] for r in mp.classify_head_surfaces(head_stats())}
        self.assertEqual({0: 'skin', 1: 'teeth', 2: 'clear', 3: 'eye', 4: 'eye', 5: 'clear', 6: 'eyelashes', 7: 'clear', 8: 'clear'}, roles)
        verts = {r['index']: r['verts'] for r in mp.classify_head_surfaces(head_stats())}
        self.assertEqual(124735, verts[0])                                           # kept so Godot can confirm the surface still matches

    def test_order_does_not_matter_only_geometry(self):
        shuffled = head_stats(list(reversed(REAL_HEAD)))
        for i, row in enumerate(shuffled):
            row['index'] = i
        roles = [r['role'] for r in mp.classify_head_surfaces(shuffled)]
        self.assertEqual(sorted(['skin', 'teeth', 'clear', 'eye', 'eye', 'clear', 'eyelashes', 'clear', 'clear']), sorted(roles))
        self.assertEqual('skin', roles[-1])                                          # the face was index 0, now last

    def test_unrecognised_meshes_return_none_instead_of_guessing(self):
        self.assertIsNone(mp.classify_head_surfaces(None))
        self.assertIsNone(mp.classify_head_surfaces(head_stats(REAL_HEAD[:3])))      # no eyes
        odd = head_stats(REAL_HEAD)
        odd[3]['verts'] = 801                                                        # eyes no longer a matching pair
        self.assertIsNone(mp.classify_head_surfaces(odd))
        no_lashes = [r for r in head_stats() if r['index'] not in (5, 6, 7, 8)]
        self.assertIsNone(mp.classify_head_surfaces(no_lashes))


class GlbCleanup(unittest.TestCase):
    @staticmethod
    def glb(doc, binary=b'\x00' * 8):
        import struct
        blob = json.dumps(doc).encode()
        blob += b' ' * (-len(blob) % 4)
        body = struct.pack('<I', len(blob)) + struct.pack('<I', 0x4E4F534A) + blob + struct.pack('<I', len(binary)) + struct.pack('<I', 0x004E4942) + binary
        return b'glTF' + struct.pack('<I', 2) + struct.pack('<I', 12 + len(body)) + body

    @staticmethod
    def parse(data):
        import struct
        return json.loads(data[20:20 + struct.unpack('<I', data[12:16])[0]])

    def test_removes_unreferenced_empty_accessors_and_renumbers(self):
        doc = {'asset': {'version': '2.0'}, 'accessors': [{'count': 3, 'type': 'VEC3'}, {'count': 0, 'type': 'SCALAR'}, {'count': 5, 'type': 'SCALAR'}, {'count': 0, 'type': 'VEC3'}],
               'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 2}]}], 'skins': [{'inverseBindMatrices': 2}]}
        out, removed = mp.clean_glb(self.glb(doc))
        got = self.parse(out)
        self.assertEqual(2, removed)
        self.assertEqual([3, 5], [a['count'] for a in got['accessors']])
        self.assertEqual({'attributes': {'POSITION': 0}, 'indices': 1}, got['meshes'][0]['primitives'][0])
        self.assertEqual(1, got['skins'][0]['inverseBindMatrices'])
        self.assertEqual(0, len(out) % 4)
        import struct
        self.assertEqual(len(out), struct.unpack('<I', out[8:12])[0])                    # total length field stays correct

    def test_leaves_the_file_alone_when_an_empty_accessor_is_used_or_nothing_is_empty(self):
        used = {'asset': {'version': '2.0'}, 'accessors': [{'count': 0}], 'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}]}
        data = self.glb(used)
        self.assertEqual((data, 0), mp.clean_glb(data))
        none = self.glb({'asset': {'version': '2.0'}, 'accessors': [{'count': 2}]})
        self.assertEqual((none, 0), mp.clean_glb(none))
        self.assertEqual((b'not a glb at all, just bytes', 0), mp.clean_glb(b'not a glb at all, just bytes'))


class NormalRepair(unittest.TestCase):
    @staticmethod
    def quad_glb(normal_z, with_tangent=True):
        """A flat two-triangle quad facing +Z with the given per-vertex normal z, as a one-primitive GLB with an embedded buffer."""
        import struct
        pos = struct.pack('<12f', 0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0)
        nor = struct.pack('<12f', *([0, 0, normal_z] * 4))
        tan = struct.pack('<16f', *([1, 0, 0, 1] * 4))
        idx = struct.pack('<6H', 0, 1, 2, 0, 2, 3) + b'\0\0\0\0'
        blob = pos + nor + tan + idx
        views = [{'buffer': 0, 'byteOffset': 0, 'byteLength': 48}, {'buffer': 0, 'byteOffset': 48, 'byteLength': 48},
                 {'buffer': 0, 'byteOffset': 96, 'byteLength': 64}, {'buffer': 0, 'byteOffset': 160, 'byteLength': 12}]
        accessors = [{'bufferView': 0, 'componentType': 5126, 'count': 4, 'type': 'VEC3'}, {'bufferView': 1, 'componentType': 5126, 'count': 4, 'type': 'VEC3'},
                     {'bufferView': 2, 'componentType': 5126, 'count': 4, 'type': 'VEC4'}, {'bufferView': 3, 'componentType': 5123, 'count': 6, 'type': 'SCALAR'}]
        attrs = {'POSITION': 0, 'NORMAL': 1}
        if with_tangent:
            attrs['TANGENT'] = 2
        doc = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': len(blob)}], 'bufferViews': views, 'accessors': accessors,
               'meshes': [{'primitives': [{'attributes': attrs, 'indices': 3}]}]}
        j = json.dumps(doc).encode()
        j += b' ' * (-len(j) % 4)
        body = struct.pack('<I', len(j)) + b'JSON' + j + struct.pack('<I', len(blob)) + b'BIN\0' + blob
        return b'glTF' + struct.pack('<I', 2) + struct.pack('<I', 12 + len(body)) + body

    @staticmethod
    def normals(data):
        import struct
        jlen = struct.unpack('<I', data[12:16])[0]
        base = 20 + jlen + 8
        return [struct.unpack_from('<3f', data, base + 48 + i * 12) for i in range(4)], json.loads(data[20:20 + jlen])

    def test_normals_pointing_against_the_geometry_are_recomputed_and_tangents_dropped(self):
        out, fixed = mp.fix_normals(self.quad_glb(-1.0))
        self.assertEqual(1, fixed)
        normals, doc = self.normals(out)
        self.assertTrue(all(abs(n[2] - 1.0) < 1e-5 for n in normals), normals)
        self.assertNotIn('TANGENT', doc['meshes'][0]['primitives'][0]['attributes'])

    def test_consistent_normals_and_tangents_are_left_alone(self):
        data = self.quad_glb(1.0)
        self.assertEqual((data, 0), mp.fix_normals(data))

    def test_repair_is_idempotent_and_ignores_non_glb_bytes(self):
        once, _ = mp.fix_normals(self.quad_glb(-1.0))
        self.assertEqual((once, 0), mp.fix_normals(once))
        self.assertEqual((b'plain bytes', 0), mp.fix_normals(b'plain bytes'))


class SkinMerge(unittest.TestCase):
    def make_skin(self, root, status='PASS', maps=None):
        from PIL import Image
        d = pathlib.Path(root) / 'skin'
        d.mkdir()
        for name in (maps if maps is not None else ['Head_Basecolor.png', 'Head_Normal.png', 'Head_SRMF.png', 'Body_Basecolor.png', 'Body_Normal.png', 'Body_SRMF.png',
                                                   'Eyes_Color.png', 'Eyes_Normal.png', 'Teeth_Color.png', 'Teeth_Normal.png', 'Eyelashes_Color.png', 'Head_Normal_Animated_WM1.png']):
            Image.new('RGBA', (64, 32), (10, 200, 30, 255)).save(d / ('MHC_X__Maps__' + name))
        (d / 'MHC_X__Masks__head_wm1_msk_01.tga').write_bytes(b'tga')
        (d / 'MHC_X__head.dna').write_bytes(b'dna')
        (d / 'result.json').write_text(json.dumps({'status': status}))
        return d

    def dest(self, root):
        d = pathlib.Path(root) / 'godot'
        (d / 'dna').mkdir(parents=True)
        return d

    def test_maps_become_slots_normals_are_green_flipped_and_the_rest_is_kept_for_reference(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            dest = self.dest(t)
            slots = mp.merge_skin(self.make_skin(t), dest, 16)
            self.assertEqual({'albedo_head', 'normal_head', 'roughness_head', 'albedo_body', 'normal_body', 'roughness_body',
                              'eye_color', 'eye_normal', 'teeth_color', 'teeth_normal', 'lashes_color'}, set(slots))
            with Image.open(dest / 'textures/skin/Head_Normal.png') as im:
                self.assertEqual((16, 8), im.size)
                self.assertEqual((10, 55, 30), im.getpixel((0, 0)))                      # DirectX -> OpenGL green flip
            with Image.open(dest / 'textures/skin/Head_Basecolor.png') as im:
                self.assertEqual((10, 200, 30), im.getpixel((0, 0)))                     # albedo untouched, alpha dropped
            ref = {f.name for f in (dest / 'textures/reference').iterdir()}
            self.assertEqual({'Head_Normal_Animated_WM1.png', 'mask_head_wm1_msk_01.tga'}, ref)           # eye/teeth/lash maps are now used, not just kept
            self.assertTrue({'eye_color', 'eye_normal', 'teeth_color', 'teeth_normal', 'lashes_color'} <= set(slots))
            with Image.open(dest / 'textures/skin/Eyelashes_Color.png') as im:
                self.assertEqual('RGBA', im.mode)                                           # the alpha channel is the strand cut-out
            with Image.open(dest / 'textures/skin/Eyes_Normal.png') as im:
                self.assertEqual((10, 55, 30), im.convert('RGB').getpixel((0, 0)))
            self.assertEqual([], list((dest / 'dna').iterdir()))                         # the Unreal stage already provides the DNA

    def test_refuses_a_failed_job_missing_albedo_or_a_non_skin_folder(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SystemExit):
                mp.merge_skin(self.make_skin(t, status='FAIL'), self.dest(t), 16)
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SystemExit):
                mp.merge_skin(self.make_skin(t, maps=['Head_Normal.png', 'Body_Normal.png']), self.dest(t), 16)
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t) / 'empty'; d.mkdir(); (d / 'result.json').write_text('{}')
            with self.assertRaises(SystemExit):
                mp.merge_skin(d, self.dest(t), 16)


if __name__ == '__main__':
    unittest.main()
