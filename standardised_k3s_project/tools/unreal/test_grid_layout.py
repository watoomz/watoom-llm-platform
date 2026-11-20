import unittest, json, copy, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from grid_layout import prepare


class GridTests(unittest.TestCase):
    def grid(self):
        return {
            "grid": {"cols": 2, "rows": 2, "cell_cm": 200},
            "cells": [
                {"col": c, "row": r, "floor": True, "walls": {"n": r == 0, "s": r == 1, "w": c == 0, "e": c == 1}}
                for r in range(2)
                for c in range(2)
            ],
            "door_edges": [[[0, 0], [1, 0]]],
        }

    def test_plan_bounds_and_unique_walls(self):
        plan = prepare(self.grid())
        self.assertEqual(len(plan["placements"]), 12)
        self.assertEqual(len(plan["floor_cells"]), 4)
        self.assertEqual(plan, prepare(self.grid()))

    def test_blocked_door_rejected(self):
        g = self.grid()
        g["cells"][0]["walls"]["e"] = True
        g["cells"][1]["walls"]["w"] = True
        with self.assertRaisesRegex(ValueError, "Door"):
            prepare(g)

    def test_asymmetric_wall_rejected(self):
        g = self.grid()
        g["cells"][0]["walls"]["e"] = True
        with self.assertRaisesRegex(ValueError, "Asymmetric"):
            prepare(g)

    def test_duplicate_or_missing_cell_rejected(self):
        for cells in [self.grid()["cells"][:-1], self.grid()["cells"] + [self.grid()["cells"][0]]]:
            g = self.grid()
            g["cells"] = cells
            with self.assertRaises(ValueError):
                prepare(g)

    def test_fractional_coordinate_rejected(self):
        g = self.grid()
        g["cells"][0]["col"] = 0.1
        with self.assertRaisesRegex(ValueError, "Integer"):
            prepare(g)

    def test_oversized_grid_rejected(self):
        g = self.grid()
        g["grid"]["cols"] = 100000
        with self.assertRaisesRegex(ValueError, "Bounded"):
            prepare(g)

    def test_disconnected_floors_rejected_unless_allowed(self):
        g = self.grid()
        g["door_edges"] = []
        for c in g["cells"]:
            c["walls"] = {"n": True, "s": True, "w": True, "e": True}
        with self.assertRaisesRegex(ValueError, "disconnected"):
            prepare(g)
        g["allow_disconnected_floors"] = True
        self.assertEqual(prepare(g)["floor_regions"], 4)
        self.assertEqual(prepare(self.grid())["floor_regions"], 1)

    def test_malformed_input_is_value_error(self):
        for door in ([[0, 0]], [[[0, 0], [1, 0], [1, 1]]], [[["a", "b"], [1, 0]]], "x"):
            g = self.grid()
            g["door_edges"] = door
            with self.assertRaises(ValueError):
                prepare(g)
        g = self.grid()
        del g["cells"][0]["floor"]
        with self.assertRaisesRegex(ValueError, "Malformed"):
            prepare(g)


if __name__ == "__main__":
    unittest.main()
