import json, unittest
from dungeon_layout import layout

class DungeonLayoutTests(unittest.TestCase):
    def test_cli_writes_the_same_layout_as_json(self):
        import os, tempfile, dungeon_layout
        out = os.path.join(tempfile.mkdtemp(), "l.json")
        dungeon_layout.main(["--seed", "7", "--rooms", "6", "--grid", "4", "--cell-size", "1500", "--room-size", "1000", "--out", out])
        with open(out) as f:
            self.assertEqual(json.load(f), layout(7, rooms=6, grid=4, cell_size=1500, room_size=1000))

    def test_replay_and_restart(self):
        for seed in range(20):
            first=layout(seed,rooms=24,levels=3)
            self.assertEqual(first,layout(seed,rooms=24,levels=3))
            self.assertEqual(first,json.loads(json.dumps(first)))
    def test_connectivity_stairs_nonoverlap(self):
        for seed in range(100):
            result=layout(seed,rooms=64,levels=4,grid=4)
            cells={(n["level"],*n["cell"]) for n in result["rooms"]}
            self.assertEqual(len(cells),64)
            graph={n["id"]:[] for n in result["rooms"]}
            for edge in result["connections"]:
                graph[edge["from"]].append(edge["to"])
                graph[edge["to"]].append(edge["from"])
                a,b=[result["rooms"][edge[k]] for k in ("from","to")]
                if edge["kind"]=="stairs":
                    self.assertEqual(a["cell"],b["cell"])
                    self.assertEqual(b["level"]-a["level"],1)
                else:
                    self.assertEqual(a["level"],b["level"])
                    self.assertEqual(sum(abs(a["cell"][i]-b["cell"][i]) for i in range(2)),1)
            seen=set();todo=[result["entrance"]]
            while todo:
                node=todo.pop()
                if node in seen:continue
                seen.add(node);todo.extend(graph[node])
            self.assertEqual(len(seen),64)
            self.assertIn(result["exit"],seen)
            self.assertEqual(len(result["stairs"]),3)
            self.assertFalse(result["native_asset_placement_verified"])
    def test_bounds_rejected(self):
        for kwargs in ({"rooms":65},{"levels":0},{"rooms":2,"levels":4},{"grid":1},
                       {"rooms":64,"levels":1,"grid":2},{"room_size":800},
                       {"seed":True},{"rooms":3.0}):
            with self.assertRaises(ValueError):
                layout(**({"seed":1}|kwargs))
    def test_seed_changes_layout(self):
        self.assertNotEqual(layout(1),layout(2))

if __name__=="__main__":unittest.main()
