import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location("ucc", pathlib.Path(__file__).with_name("unreal_creek_check.py"))
ucc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ucc)

TEXT = ("(Position=(Points=((InVal=0.0,OutVal=(X=1,Y=2,Z=100)),(InVal=1.0,OutVal=(X=3,Y=4,Z=90)),(InVal=2.0,OutVal=(X=5,Y=6,Z=80))))"
        ",Rotation=(Points=((InVal=0.0,OutVal=(X=0,Y=0,Z=0)),(InVal=1.0,OutVal=(X=1,Y=1,Z=1)))))")


def hit(z, label="ZAS_Landscape"):
    return {"hit": True, "actorLabel": label, "location": {"z": z}}


class CreekCheck(unittest.TestCase):
    def test_only_position_points_are_read(self):
        self.assertEqual(ucc.spline_points(TEXT), [(1, 2, 100), (3, 4, 90), (5, 6, 80)])

    def test_trace_request_goes_straight_down(self):
        t = ucc.trace_request([(1, 2, 100)])["traces"][0]
        self.assertEqual((t["start"]["x"], t["end"]["x"], t["start"]["z"], t["end"]["z"]), (1, 1, 20000, 0))

    def test_buried_runs_and_tolerance(self):
        pts = [(0, 0, 100)] * 5
        res = [hit(110), hit(200), hit(250), hit(100), hit(500)]
        rows, runs = ucc.analyse(pts, res, tol=30)
        self.assertEqual(runs, [(1, 2), (4, 4)])
        self.assertEqual(rows[0][4], "ok")

    def test_lake_hit_is_not_counted(self):
        rows, runs = ucc.analyse([(0, 0, 100)], [hit(900, "Lake_1")])
        self.assertEqual(runs, [])
        self.assertTrue(rows[0][4].startswith("other:"))


if __name__ == "__main__":
    unittest.main()
