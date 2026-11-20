"""gg_dungeon: every test here is pure logic (catalog schema, rotation geometry, the layout generator and its
independent verifier, and filesystem scanning for catalog-init). Nothing needs Godot/numpy-only, no engine, no
real converted kit: that is the point of this stage (see the module docstring and references/gg-dungeon.md).
There is nothing engine-gated to skip here, unlike test_gg_catalog/test_gg_ui."""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_dungeon as D, gg_godot


def piece(**kw):
    p = {"kind": "room", "scene": "res://d/x.tscn", "footprint": [2, 2], "sockets": [{"edge": "north", "pos": 0}], "notes": ""}
    p.update(kw)
    return p


ROOM = {"kind": "room", "scene": "res://d/room.tscn", "footprint": [2, 2],
        "sockets": [{"edge": "north", "pos": 0}, {"edge": "south", "pos": 0}, {"edge": "east", "pos": 0}, {"edge": "west", "pos": 0}]}
CORRIDOR = {"kind": "corridor", "scene": "res://d/corridor.tscn", "footprint": [1, 2], "sockets": [{"edge": "north", "pos": 0}, {"edge": "south", "pos": 0}]}


def synth_catalog():
    return {"schema": 1, "cell_m": 4.0, "pieces": {"room": dict(ROOM), "corridor": dict(CORRIDOR)}}


class PieceSchema(unittest.TestCase):
    def test_default_piece_is_valid(self):
        self.assertEqual(D.piece_errors("room_a", piece()), [])

    def test_rules(self):
        cases = [
            (piece(kind="nope"), "not one of"),
            (piece(scene="d/x.tscn"), "res://"),
            (piece(footprint=[0, 2]), "within 1.."),
            (piece(footprint=["a", 2]), "two integers"),
            (piece(footprint=[2, 2, 2]), "two integers"),
            (piece(sockets="nope"), "sockets must be a list"),
            (piece(sockets=[{"edge": "north"}]), "exactly 'edge' and 'pos'"),
            (piece(sockets=[{"edge": "north", "pos": 0, "extra": 1}]), "exactly 'edge' and 'pos'"),
            (piece(sockets=[{"edge": "nowhere", "pos": 0}]), "not one of"),
            (piece(sockets=[{"edge": "north", "pos": "x"}]), "pos must be an integer"),
            (piece(sockets=[{"edge": "north", "pos": 2}]), "outside 0.."),
            (piece(sockets=[{"edge": "north", "pos": -1}]), "outside 0.."),
            (piece(sockets=[{"edge": "north", "pos": 0}, {"edge": "north", "pos": 0}]), "duplicate socket"),
            (piece(kind="corridor", sockets=[]), "needs at least one socket"),
            (piece(bogus=1), "unknown key"),
        ]
        for p, frag in cases:
            errs = D.piece_errors("x", p)
            self.assertTrue(any(frag in e for e in errs), (frag, errs))

    def test_prop_may_have_no_sockets(self):
        self.assertEqual(D.piece_errors("deco", piece(kind="prop", sockets=[])), [])

    def test_socket_pos_bound_depends_on_axis(self):
        # footprint [2, 3]: north/south range over width (0..1), east/west range over depth (0..2)
        p = piece(footprint=[2, 3], sockets=[{"edge": "north", "pos": 1}, {"edge": "east", "pos": 2}])
        self.assertEqual(D.piece_errors("x", p), [])
        self.assertTrue(any("outside 0..1" in e for e in D.piece_errors("x", piece(footprint=[2, 3], sockets=[{"edge": "north", "pos": 2}]))))
        self.assertTrue(any("outside 0..2" in e for e in D.piece_errors("x", piece(footprint=[2, 3], sockets=[{"edge": "east", "pos": 3}]))))

    def test_name_shape(self):
        for bad in ("Room", "../x", "", "1room", "a b"):
            self.assertTrue(D.piece_errors(bad, piece()), bad)
        self.assertEqual(D.piece_errors("room_2", piece()), [])

    def test_validate_catalog_shape(self):
        self.assertIn("no pieces", " ".join(D.validate({"schema": 1, "cell_m": 4.0, "pieces": {}})))
        self.assertIn("schema", " ".join(D.validate({"cell_m": 4.0, "pieces": {"a": piece()}})))
        self.assertIn("cell_m", " ".join(D.validate({"schema": 1, "cell_m": 0, "pieces": {"a": piece()}})))
        self.assertEqual(D.validate(synth_catalog()), [])


class Rotation(unittest.TestCase):
    def test_corridor_rotates_from_ns_to_ew(self):
        fp1, sk1 = D.rotate_once((1, 2), [{"edge": "north", "pos": 0}, {"edge": "south", "pos": 0}])
        self.assertEqual(fp1, (2, 1))
        self.assertEqual(sorted((s["edge"], s["pos"]) for s in sk1), [("east", 0), ("west", 0)])

    def test_edge_cycle_is_n_e_s_w(self):
        # footprint (w=3, d=5); the pos transform on e->s / w->n uses the CURRENT footprint's depth at that step,
        # not the original one -- this walks the full cycle and checks each intermediate shape explicitly.
        fp1, sk1 = D.rotate_once((3, 5), [{"edge": "north", "pos": 2}])
        self.assertEqual((fp1, sk1), ((5, 3), [{"edge": "east", "pos": 2}]))
        fp2, sk2 = D.rotate_once(fp1, sk1)
        self.assertEqual((fp2, sk2), ((3, 5), [{"edge": "south", "pos": 0}]))  # d of fp1 is 3: 3-1-2=0
        fp3, sk3 = D.rotate_once(fp2, sk2)
        self.assertEqual((fp3, sk3), ((5, 3), [{"edge": "west", "pos": 0}]))
        fp4, sk4 = D.rotate_once(fp3, sk3)
        self.assertEqual((fp4, sk4), ((3, 5), [{"edge": "north", "pos": 2}]))  # d of fp3 is 3: 3-1-0=2

    def test_four_rotations_is_identity_for_any_shape(self):
        for fp, sk in (((2, 2), [{"edge": "north", "pos": 0}, {"edge": "north", "pos": 1}, {"edge": "east", "pos": 0}]),
                       ((1, 3), [{"edge": "east", "pos": 2}, {"edge": "west", "pos": 0}]),
                       ((4, 1), [{"edge": "north", "pos": 3}, {"edge": "south", "pos": 0}])):
            rfp, rsk = D.rotate(fp, sk, 4)
            self.assertEqual(rfp, fp)
            self.assertEqual(sorted((s["edge"], s["pos"]) for s in rsk), sorted((s["edge"], s["pos"]) for s in sk))

    def test_rotate_does_not_mutate_input(self):
        sk = [{"edge": "north", "pos": 0}]
        D.rotate((1, 1), sk, 1)
        self.assertEqual(sk, [{"edge": "north", "pos": 0}])

    def test_piece_at_refuses_unknown_piece(self):
        with self.assertRaisesRegex(gg_godot.Refused, "not in the catalog"):
            D.piece_at(synth_catalog(), "nope", 0)


class Geometry(unittest.TestCase):
    def test_socket_anchor_and_outside(self):
        fp = (2, 3)
        self.assertEqual(D.socket_anchor((10, 20), fp, {"edge": "north", "pos": 1}), (11, 20))
        self.assertEqual(D.socket_outside((10, 20), fp, {"edge": "north", "pos": 1}), (11, 19))
        self.assertEqual(D.socket_anchor((10, 20), fp, {"edge": "south", "pos": 1}), (11, 22))
        self.assertEqual(D.socket_outside((10, 20), fp, {"edge": "south", "pos": 1}), (11, 23))
        self.assertEqual(D.socket_anchor((10, 20), fp, {"edge": "east", "pos": 2}), (11, 22))
        self.assertEqual(D.socket_outside((10, 20), fp, {"edge": "east", "pos": 2}), (12, 22))
        self.assertEqual(D.socket_anchor((10, 20), fp, {"edge": "west", "pos": 2}), (10, 22))
        self.assertEqual(D.socket_outside((10, 20), fp, {"edge": "west", "pos": 2}), (9, 22))

    def test_footprint_cells(self):
        self.assertEqual(D.footprint_cells((0, 0), (2, 1)), {(0, 0), (1, 0)})
        self.assertEqual(len(D.footprint_cells((5, 5), (3, 4))), 12)


class LayoutGenerator(unittest.TestCase):
    def test_deterministic_for_the_same_seed(self):
        cat = synth_catalog()
        a = D.build_layout(cat, 42, 8)
        b = D.build_layout(cat, 42, 8)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_different_seeds_usually_differ(self):
        cat = synth_catalog()
        outs = {json.dumps(D.build_layout(cat, s, 8), sort_keys=True) for s in range(5)}
        self.assertGreater(len(outs), 1)

    def test_places_the_requested_rooms_and_passes_verify(self):
        cat = synth_catalog()
        for seed in range(6):
            m = D.build_layout(cat, seed, 8)
            self.assertEqual(m["placed_rooms"], 8, seed)
            self.assertLessEqual(m["placed_rooms"], m["requested_rooms"])
            rows, ok = D.verify_layout(cat, m)
            self.assertTrue(ok, (seed, rows))

    def test_rooms_one_is_just_the_start(self):
        m = D.build_layout(synth_catalog(), 1, 1)
        self.assertEqual((m["placed_rooms"], len(m["instances"])), (1, 1))
        self.assertEqual(m["instances"][0]["piece"], "room")

    def test_a_single_room_piece_can_serve_as_its_own_connector(self):
        cat = {"schema": 1, "cell_m": 4.0, "pieces": {"room": dict(ROOM)}}
        m = D.build_layout(cat, 3, 6)
        self.assertEqual(m["placed_rooms"], 6)
        rows, ok = D.verify_layout(cat, m)
        self.assertTrue(ok, rows)

    def test_refuses_without_a_room_piece(self):
        cat = {"schema": 1, "cell_m": 4.0, "pieces": {"corridor": dict(CORRIDOR)}}
        with self.assertRaisesRegex(gg_godot.Refused, "kind='room'"):
            D.build_layout(cat, 1, 3)

    def test_refuses_without_any_socket_anywhere(self):
        cat = {"schema": 1, "cell_m": 4.0, "pieces": {"room": {"kind": "room", "scene": "res://x.tscn", "footprint": [1, 1], "sockets": []}}}
        with self.assertRaisesRegex(gg_godot.Refused, "cannot connect anything"):
            D.build_layout(cat, 1, 3)

    def test_rooms_bound_is_enforced_by_layout_cmd(self):
        with tempfile.TemporaryDirectory() as d:
            D.save_catalog(d, synth_catalog())
            with self.assertRaises(gg_godot.Refused):
                D.layout_cmd(d, 1, 0)
            with self.assertRaises(gg_godot.Refused):
                D.layout_cmd(d, 1, D.MAX_ROOMS + 1)
            with self.assertRaises(gg_godot.Refused):
                D.layout_cmd(d, 1, 3, name="bad/name")


class VerifyCatchesBrokenLayouts(unittest.TestCase):
    """verify_layout recomputes connectivity itself: feed it hand-built layouts a real generator would never
    produce, to prove it does not just trust the 'connections' list or the room count."""

    def test_disconnected_room_fails(self):
        cat = synth_catalog()
        layout = {"schema": 1, "entrance": 0, "instances": [
            {"id": 0, "piece": "room", "x": 0, "z": 0, "rot": 0},
            {"id": 1, "piece": "room", "x": 50, "z": 50, "rot": 0},  # far away, no matching socket pair
        ], "connections": [{"a": 0, "a_edge": "north", "a_pos": 0, "b": 1, "b_edge": "south", "b_pos": 0}]}  # a lie
        rows, ok = D.verify_layout(cat, layout)
        self.assertFalse(ok)
        self.assertFalse(dict((n, o) for n, o, _ in rows)["every room reachable from the entrance"])

    def test_overlapping_instances_fail(self):
        cat = synth_catalog()
        layout = {"schema": 1, "entrance": 0, "instances": [
            {"id": 0, "piece": "room", "x": 0, "z": 0, "rot": 0},
            {"id": 1, "piece": "room", "x": 1, "z": 1, "rot": 0},  # overlaps instance 0's footprint
        ], "connections": []}
        rows, ok = D.verify_layout(cat, layout)
        self.assertFalse(ok)
        self.assertFalse(dict((n, o) for n, o, _ in rows)["no footprint overlaps"])

    def test_a_correctly_connected_pair_passes(self):
        cat = synth_catalog()
        layout = {"schema": 1, "entrance": 0, "instances": [
            {"id": 0, "piece": "room", "x": 0, "z": 0, "rot": 0},
            {"id": 1, "piece": "corridor", "x": 1, "z": -2, "rot": 1},  # east of room 0's east socket, rotated to face west/east
        ], "connections": []}
        # room footprint (2,2); its east socket at pos0 anchors (1,0), opens at (2,0). corridor rotated 1 (fp (2,1)) has
        # a west socket at pos0 anchoring (0,0) in local coords: place its origin at (2,0) so local (0,0) lands at (2,0).
        layout["instances"][1] = {"id": 1, "piece": "corridor", "x": 2, "z": 0, "rot": 1}
        rows, ok = D.verify_layout(cat, layout)
        self.assertTrue(ok, rows)

    def test_empty_instances_is_a_clean_failure_not_a_crash(self):
        rows, ok = D.verify_layout(synth_catalog(), {"instances": []})
        self.assertFalse(ok)
        self.assertIn("no instances", rows[0][2])

    def test_unknown_piece_in_layout_is_a_clean_failure(self):
        layout = {"entrance": 0, "instances": [{"id": 0, "piece": "ghost", "x": 0, "z": 0, "rot": 0}]}
        rows, ok = D.verify_layout(synth_catalog(), layout)
        self.assertFalse(ok)
        self.assertIn("ghost", rows[0][2])


class CatalogInitScan(unittest.TestCase):
    def test_scan_finds_tscn_and_glb_recursively_and_ignores_others(self):
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "assets", "kit1")
            os.makedirs(os.path.join(base, "sub"))
            for rel in ("a.tscn", "b.glb", "c.txt", "sub/d.tscn"):
                open(os.path.join(base, rel), "w").write("x")
            found = D.scan_pieces_dir(d, "res://assets/kit1")
            self.assertEqual(found, ["res://assets/kit1/a.tscn", "res://assets/kit1/b.glb", "res://assets/kit1/sub/d.tscn"])

    def test_scan_refuses_bad_paths(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(gg_godot.Refused):
                D.scan_pieces_dir(d, "assets/kit1")
            with self.assertRaises(gg_godot.Refused):
                D.scan_pieces_dir(d, "res://../kit1")
            with self.assertRaises(gg_godot.Refused):
                D.scan_pieces_dir(d, "res://missing")

    def test_stub_name_is_valid_and_deduplicates(self):
        used = set()
        n1 = D.stub_name("res://kit/Room A (1).tscn", used)
        used.add(n1)
        n2 = D.stub_name("res://kit/Room A (1).glb", used)
        self.assertTrue(D.NAME_RE.match(n1))
        self.assertTrue(D.NAME_RE.match(n2))
        self.assertNotEqual(n1, n2)

    def test_catalog_init_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "kit")
            os.makedirs(base)
            open(os.path.join(base, "room.tscn"), "w").write("x")
            code, rep = D.catalog_init(d, "res://kit", dry_run=True)
            self.assertEqual(code, 0)
            self.assertEqual(rep["would_add"], ["res://kit/room.tscn"])
            self.assertFalse(os.path.exists(D.catalog_path(d)))

    def test_catalog_init_writes_unclassified_stubs_then_refuses_a_second_time(self):
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "kit")
            os.makedirs(base)
            for n in ("room_a.tscn", "corridor_b.glb"):
                open(os.path.join(base, n), "w").write("x")
            code, rep = D.catalog_init(d, "res://kit", dry_run=False)
            self.assertEqual(code, 0)
            cat = D.load_catalog(d)
            self.assertEqual(set(cat["pieces"]), set(rep["pieces"]))
            for p in cat["pieces"].values():
                self.assertEqual(p["kind"], "unclassified")
            errs = D.validate(cat)
            self.assertTrue(any("not one of" in e for e in errs))  # unclassified fails validate until hand-edited
            with self.assertRaises(gg_godot.Refused):
                D.catalog_init(d, "res://kit")

    def test_catalog_init_refuses_an_empty_pieces_dir(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "kit"))
            with self.assertRaises(gg_godot.Refused):
                D.catalog_init(d, "res://kit")


class EndToEndViaFiles(unittest.TestCase):
    def test_layout_then_verify_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            D.save_catalog(d, synth_catalog())
            code, rep = D.layout_cmd(d, 7, 8, name="my_layout")
            self.assertEqual(code, 0, rep)
            self.assertTrue(os.path.isfile(D.layout_path(d, "my_layout")))
            code2, rep2 = D.verify_cmd(d, "my_layout")
            self.assertEqual(code2, 0, rep2)
            self.assertTrue(all(ok for _, ok, _ in rep2["rows"]))

    def test_verify_refuses_without_a_layout_file(self):
        with tempfile.TemporaryDirectory() as d:
            D.save_catalog(d, synth_catalog())
            with self.assertRaisesRegex(gg_godot.Refused, "run gg_dungeon.py layout first"):
                D.verify_cmd(d)

    def test_layout_refuses_an_invalid_catalog(self):
        with tempfile.TemporaryDirectory() as d:
            D.save_catalog(d, {"schema": 1, "cell_m": 4.0, "pieces": {"a": piece(kind="nope")}})
            with self.assertRaisesRegex(gg_godot.Refused, "catalog-validate"):
                D.layout_cmd(d, 1, 3)

    def test_load_catalog_errors(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(gg_godot.Refused, "catalog-init"):
                D.load_catalog(d)
            open(D.catalog_path(d), "w").write("{bad")
            with self.assertRaisesRegex(gg_godot.Refused, "not valid JSON"):
                D.load_catalog(d)


class CLI(unittest.TestCase):
    def test_full_cli_flow(self):
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "kit")
            os.makedirs(base)
            open(os.path.join(base, "room.tscn"), "w").write("x")
            self.assertEqual(D.main(["catalog-init", "--project", d, "--pieces-dir", "res://kit"]), 0)
            self.assertEqual(D.main(["catalog-list", "--project", d]), 0)
            self.assertEqual(D.main(["catalog-validate", "--project", d]), 1)  # still unclassified
            cat = D.load_catalog(d)
            name = next(iter(cat["pieces"]))
            cat["pieces"][name] = dict(ROOM, scene=cat["pieces"][name]["scene"])
            D.save_catalog(d, cat)
            self.assertEqual(D.main(["catalog-validate", "--project", d]), 0)
            self.assertEqual(D.main(["layout", "--project", d, "--seed", "5", "--rooms", "4"]), 0)
            self.assertEqual(D.main(["verify", "--project", d]), 0)

    def test_cli_refusals_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(D.main(["catalog-list", "--project", d]), 2)
            self.assertEqual(D.main(["catalog-init", "--project", d, "--pieces-dir", "not-res"]), 2)


if __name__ == "__main__":
    unittest.main()
