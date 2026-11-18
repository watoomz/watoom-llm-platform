import collections
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unreal_dungeon as ud  # noqa: E402

SPEC = {"origin": [1000, 2000, 500],
        "modules": {"wall": "/W", "door": "/D", "floor": "/F", "column": "/C", "wall_len": 500, "wall_thick": 155, "wall_height": 753},
        "light": {"intensity": 8000},
        "entrance": {"location": [0, 0, 900], "extent": [150, 300, 300]},
        "exit_to": [50, 60, 70, 180]}


def two_rooms(dx=2000, dy=0, size=1500):
    return {"rooms": [{"id": 0, "level": 0, "position": [0, 0, 0], "size": [size, size]},
                      {"id": 1, "level": 0, "position": [dx, dy, 0], "size": [size, size]}],
            "connections": [{"from": 0, "to": 1, "kind": "corridor"}], "entrance": 0, "exit": 1}


def placed(c):
    return [a for p in c["phases"] for m, a in p["calls"] if m == "level.place_actor"]


class Dungeon(unittest.TestCase):
    def test_rooms_get_walls_with_a_doorway_facing_the_corridor(self):
        c = ud.calls(two_rooms(), SPEC)
        kinds = collections.Counter(a["staticMesh"] for a in placed(c) if a["actorClass"] == "StaticMeshActor")
        # 2 rooms x 4 sides x 3 segments = 24 slots, 2 of them doors; + corridor 1 segment long = 2 walls
        self.assertEqual(kinds["/D"], 2)
        self.assertEqual(kinds["/W"], 22 + 2)
        self.assertEqual(kinds["/F"], 2 * 2 + 2 + 2 * 4)        # floor+ceiling per room and corridor, 4 corner posts per room
        doors = [a for a in placed(c) if a.get("staticMesh") == "/D"]
        # entrance room at origin x 1000: its east doorway sits on the room edge + half a wall, on the corridor line
        self.assertEqual(sorted(round(d["location"]["x"]) for d in doors), [1000 + 750 + 78, 3000 - 750 - 78])
        self.assertTrue(all(d["location"]["y"] == 2000 for d in doors))

    def test_corridor_walls_run_along_it_on_both_sides(self):
        c = ud.calls(two_rooms(dx=0, dy=2000), SPEC)
        walls = [a for a in placed(c) if a.get("staticMesh") == "/W" and a["location"]["y"] == 2000 + 1000]
        self.assertEqual(sorted(round(w["location"]["x"]) for w in walls), [1000 - 328, 1000 + 328])   # 250 + 77.5
        self.assertTrue(all(w["rotation"]["yaw"] == 90.0 for w in walls))

    def test_portals_lead_in_and_out(self):
        c = ud.calls(two_rooms(), SPEC)
        props = {(a["actorLabel"], a["propertyName"]): a["value"] for p in c["phases"] for m, a in p["calls"] if m == "level.set_actor_property"}
        self.assertEqual(props[("ZAS_Dgn_Portal_In", "Destination")], "(X=1000,Y=2000,Z=620)")
        self.assertEqual(props[("ZAS_Dgn_Portal_Out", "Destination")], "(X=50,Y=60,Z=70)")
        self.assertEqual(props[("ZAS_Dgn_Portal_Out", "DestinationYaw")], 180.0)
        out = [a for a in placed(c) if a["label"] == "ZAS_Dgn_Portal_Out"][0]
        self.assertEqual((out["location"]["x"], out["location"]["y"]), (3000, 2000))

    def test_even_segment_rooms_and_odd_corridors_are_refused(self):
        with self.assertRaises(ValueError):
            ud.calls(two_rooms(size=1000), SPEC)            # 2 segments: no middle doorway
        with self.assertRaises(ValueError):
            ud.calls(two_rooms(dx=1800), SPEC)              # 300 cm corridor is not a wall length

    def test_bounds_include_the_walls(self):
        x0, y0, x1, y1, z0, z1 = ud.bounds(two_rooms(), SPEC)
        self.assertEqual((x0, x1, z1), (1000 - 750 - 155, 3000 + 750 + 155, 500 + 753 + 50))


class Labels(unittest.TestCase):
    def test_labels_name_the_piece_and_rebuild_clears_the_prefix(self):
        c = ud.calls(two_rooms(), SPEC, rebuild=True)
        labels = [a["label"] for a in placed(c)]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertIn("ZAS_Dgn_R0_DoorE1", labels)
        self.assertIn("ZAS_Dgn_C0_1_WallL0", labels)
        first = c["phases"][0]["calls"]
        self.assertIn(["level.delete_actors", {"labelPrefix": "ZAS_Dgn_"}], first)

    def test_room_slabs_cover_the_wall_ring(self):
        c = ud.calls(two_rooms(), SPEC)
        fl = [a for a in placed(c) if a["label"] == "ZAS_Dgn_R0_Floor"][0]
        self.assertEqual(fl["scale"]["x"], (1500 + 2 * 155) / 100)


if __name__ == "__main__":
    unittest.main()
