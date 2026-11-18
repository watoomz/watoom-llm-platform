import copy, json, math, os, sys, tempfile, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_godot, gg_player as G, gg_scatter as S


class W:
    """Fake world: 65x65 cells of 4 m, flat at 5 m above the sea unless changed; water only in the sea cells."""
    def __init__(self, h=5.0, dist=100.0):
        self.cell, self.sea = 4.0, 0.0
        self.h = np.full((65, 65), float(h))
        self.dist = np.full((65, 65), float(dist))
        gy, gx = np.gradient(self.h, self.cell)
        self.slope = np.hypot(gx, gy)
        self.wd = {"size_m": [256.0, 256.0]}


def prof(view="third_person"):
    p = {"dimension": "3d", "view": view, "world": {"size_m": [256.0, 256.0]}, "level": "main"}
    p["player"], p["camera"] = G.default_sections(p)
    return p


def good_trace(p, world, start, walk_s=2.0):
    """What a correct run looks like on flat ground."""
    steps, ph, dx = G.make_script(p, walk_s)
    total = sum(s["ticks"] for s in steps)
    sp, ac, g = p["player"]["speed_mps"], p["player"]["accel_mps2"], p["player"]["gravity_mps2"]
    rows, x, z, yaw, y, vy, v = [], start["position"][0], start["position"][2], start["yaw_deg"], 5.0, 0.0, 0.0
    jv = math.sqrt(2 * g * p["player"]["jump_height_m"])
    for k in range(total):
        inwalk = ph["walk1"][0] <= k < ph["walk1"][1] or ph["walk2"][0] <= k < ph["walk2"][1]
        v = min(sp, v + ac / 60.0) if inwalk else max(0.0, v - ac / 60.0)
        world_rel = p["camera"]["mode"] in ("top_down", "isometric")
        if "turn" in ph and k == ph["turn"][0] + 1:
            yaw += -dx * p["camera"]["mouse_sens_deg_per_px"]
        if world_rel:
            dirv = (0.0, -1.0) if k < ph["walk2"][0] else (1.0, 0.0)
        else:
            dirv = (-math.sin(math.radians(yaw)), -math.cos(math.radians(yaw)))
        x += dirv[0] * v / 60.0
        z += dirv[1] * v / 60.0
        if ph["jump"][0] + 2 <= k < ph["jump"][1]:
            if k == ph["jump"][0] + 2:
                vy = jv
            vy -= g / 60.0
            y = max(5.0, y + vy / 60.0)
            if y == 5.0:
                vy = 0.0
        floor = y <= 5.0 + 1e-9
        rows.append([k + 1, x, y, z, yaw, floor, vy, x, y + 1.6, z])
    return rows, ph, dx


START = {"position": [128.0, 5.0, 128.0], "yaw_deg": 0.0, "runway": [[128.0, 128.0 - d] for d in range(1, 13)], "runway_m": 12.0}


class T(unittest.TestCase):
    def test_defaults_valid_for_every_3d_view(self):
        for v in ("first_person", "third_person", "top_down", "isometric"):
            self.assertEqual(G.validate_player(prof(v)), [], v)

    def test_validation_names_key_value_and_fix(self):
        cases = [("player", "speed_mps", 40, "player.speed_mps = 40 is outside 0.5..20"), ("player", "jump_height_m", -1, "jump_height_m"), ("player", "radius_m", 0.01, "radius_m"),
                 ("camera", "fov_deg", 10, "camera.fov_deg"), ("camera", "pitch_deg", 80, "pitch_deg"), ("camera", "mode", "bogus", "camera.mode")]
        for sec, k, v, frag in cases:
            p = prof(); p[sec][k] = v
            errs = G.validate_player(p)
            self.assertTrue(any(frag in e for e in errs), (k, errs))
        p = prof(); p["player"]["speed_mps"] = 40
        self.assertIn("3..8", " ".join(G.validate_player(p)))

    def test_cross_key_refusals(self):
        for mut, frag in ((lambda p: p["camera"].update(eye_height_m=2.0), "eye is inside the body"), (lambda p: p["player"].update(radius_m=1.0, height_m=1.5), "half of player.height_m"),
                          (lambda p: p["player"]["start"].update(max_slope=1.0), "cannot stand on"), (lambda p: p["camera"].update(far_m=100), "world diagonal"),
                          (lambda p: p["player"]["start"].update(runway_m=100.0, edge_margin_m=60.0), "half the smaller world side"), (lambda p: p["player"]["start"].update(runway_m=6.0), "too short"),
                          (lambda p: p["camera"].update(mode="first_person"), "does not match the project view"), (lambda p: p["player"].update(bogus=1), "player.bogus is not a key"),
                          (lambda p: p["player"]["start"].update(rule="fixed"), "position_xz")):
            p = prof(); mut(p)
            self.assertTrue(any(frag in e for e in G.validate_player(p)), frag)
        p = prof(); p["dimension"] = "2d"
        self.assertIn("2D players are not built yet", G.validate_player(p)[0])
        p = prof(); del p["camera"]
        self.assertIn("gg_player.py init", G.validate_player(p)[0])

    def test_start_rule_picks_dry_gentle_clear_ground_deterministically(self):
        w = W(); st = copy.deepcopy(prof()["player"]["start"])
        a = G.choose_start(w, st, [])
        self.assertEqual(a, G.choose_start(w, st, []))
        x, y, z = a["position"]
        self.assertGreaterEqual(y - w.sea, st["min_above_sea_m"])
        self.assertEqual(len(a["runway"]), 12 + 0 if False else int(st["runway_m"]))
        # a tree 6 m ahead of every heading near the centre removes those starts: result stays clear of every solid
        solids = [[x + dx, z + dz, 1.0] for dx in (-6, 0, 6) for dz in (-6, 0, 6) if (dx, dz) != (0, 0)]
        b = G.choose_start(w, st, solids)
        for sx, sz, r in solids:
            self.assertGreater(math.hypot(b["position"][0] - sx, b["position"][2] - sz) - r, st["clear_m"] - 1e-6)
            for px, pz in b["runway"]:
                self.assertGreater(math.hypot(px - sx, pz - sz) - r, 0.8)

    def test_start_rule_world_relative_faces_minus_z_with_clear_sideways_leg(self):
        w = W(); st = copy.deepcopy(prof("top_down")["player"]["start"])
        a = G.choose_start(w, st, [], world_rel=True)
        self.assertEqual(a["yaw_deg"], 0.0)

    def test_start_rule_refusals_name_the_rule(self):
        sea = W(h=-5.0)
        with self.assertRaises(gg_godot.Refused) as c: G.choose_start(sea, copy.deepcopy(prof()["player"]["start"]), [])
        self.assertIn("player.start.min_above_sea_m", str(c.exception))
        st = copy.deepcopy(prof()["player"]["start"]); st.update(rule="fixed", position_xz=[10.0, 10.0], yaw_deg=0.0)
        with self.assertRaises(gg_godot.Refused) as c: G.choose_start(sea, st, [])
        self.assertIn("above the sea", str(c.exception))
        w = W(); st.update(position_xz=[400.0, 10.0])
        with self.assertRaises(gg_godot.Refused) as c: G.choose_start(w, st, [])
        self.assertIn("outside the world", str(c.exception))
        wall = [[x, z, 3.0] for x in range(0, 257, 5) for z in range(0, 257, 5)]
        with self.assertRaises(gg_godot.Refused) as c: G.choose_start(W(), copy.deepcopy(prof()["player"]["start"]), wall)
        self.assertIn("clear", str(c.exception))

    def test_start_yaw_convention(self):
        self.assertAlmostEqual(G.yaw_of(0, -1), 0.0)       # -Z is yaw 0
        self.assertAlmostEqual(G.yaw_of(1, 0), -90.0)      # +X is yaw -90 (a turn right is a negative yaw)
        self.assertAlmostEqual(abs(G.yaw_of(0, 1)), 180.0)

    def test_good_traces_pass_every_check_in_every_mode(self):
        for v in ("first_person", "third_person", "top_down", "isometric"):
            p = prof(v); w = W()
            rows, ph, dx = good_trace(p, w, START)
            ev = {}
            self.assertEqual(G.evaluate(rows, ph, dx, p, w, START, ev), [], v)
            self.assertGreater(ev["distance_m"], 2.0)

    def mutate(self, f, **kw):
        p = prof(); w = kw.get("world") or W()
        rows, ph, dx = good_trace(p, w, START)
        t = np.array(rows, dtype=float); f(t, ph); fails = G.evaluate(t.tolist(), ph, dx, p, w, START, {})
        return [x.split(":")[0] for x in fails]

    def test_each_check_fails_alone_for_its_own_fault(self):
        def fall(t, ph): t[ph["walk1"][0]:, 2] -= np.linspace(0, 20, len(t) - ph["walk1"][0])
        self.assertIn("C2 fall-through", self.mutate(fall))
        def not_floor(t, ph): t[:ph["settle"][1], 5] = 0
        self.assertIn("C1 settle", self.mutate(not_floor))
        def still(t, ph): t[:, 1] = START["position"][0]; t[:, 3] = START["position"][2]
        self.assertIn("C3 distance", self.mutate(still))
        def slow(t, ph):
            a, b = ph["walk1"]; t[a:b + 1, 3] = START["position"][2] - (t[a:b + 1, 3] * 0 + np.linspace(0, 5, b - a + 1))
        self.assertIn("C3 distance", self.mutate(slow))
        def noturn(t, ph): t[:, 4] = 0.0
        self.assertIn("C4 mouse turn", self.mutate(noturn))
        def sideways(t, ph):
            a, b = ph["walk1"]; d = t[b, 3] - t[a, 3]; t[a:b + 1, 1] = START["position"][0] + np.linspace(0, -d, b - a + 1); t[a:b + 1, 3] = START["position"][2]
        self.assertIn("C4 heading", self.mutate(sideways))
        def nojump(t, ph): t[ph["jump"][0]:, 2] = 5.0; t[ph["jump"][0]:, 5] = 1
        self.assertIn("C5 jump", self.mutate(nojump))
        def below_cam(t, ph): t[:, 8] = t[:, 2] - 3.0
        self.assertIn("C7 camera", self.mutate(below_cam))
        wet = W(); wet.dist[:] = 0.0
        self.assertIn("C6 sea", self.mutate(lambda t, ph: None, world=wet))

    def test_faults_do_not_trigger_unrelated_checks(self):
        def below_cam(t, ph): t[:, 8] = t[:, 2] - 3.0
        self.assertEqual(self.mutate(below_cam), ["C7 camera"])
        def noturn(t, ph): t[:, 4] = 0.0
        got = set(self.mutate(noturn))
        self.assertIn("C4 mouse turn", got)
        self.assertTrue(got <= {"C4 mouse turn", "C4 second walk"}, got)    # the second walk then also heads off the (unchanged) facing: a real consequence, nothing unrelated

    def test_blocked_player_cannot_shrink_its_own_target(self):
        p = prof(); w = W(); rows, ph, dx = good_trace(p, w, START)
        t = np.array(rows, dtype=float); a, b = ph["walk1"]
        t[a + 20:b + 1, 1] = t[a + 20, 1]; t[a + 20:b + 1, 3] = t[a + 20, 3]       # stops after 20 ticks against an obstacle
        fails = G.evaluate(t.tolist(), ph, dx, p, w, START, {})
        self.assertTrue(any(f.startswith("C3 distance") for f in fails))
        steep = W(); steep.h = np.tile(np.arange(65) * 0.0, (65, 1)) + 5.0
        slope_start = dict(START, position=[128.0, 5.0, 128.0])
        self.assertEqual(G.evaluate(good_trace(p, steep, slope_start)[0], ph, dx, p, steep, slope_start, {}), [])

    def test_script_and_walk_follow_the_runway(self):
        p = prof()
        steps, ph, dx = G.make_script(p, 3.0)
        self.assertEqual(sum(s["ticks"] for s in steps), ph["jump"][1])
        self.assertAlmostEqual(dx * p["camera"]["mouse_sens_deg_per_px"], 90.0)
        self.assertNotIn("turn", G.make_script(prof("top_down"), 3.0)[1])
        self.assertAlmostEqual(G.effective_walk_s(p, 3.0, 12.0), (12 - 2) / 5.0 + 5.0 / 80.0)
        self.assertEqual(G.effective_walk_s(p, 3.0, 100.0), 3.0)
        self.assertEqual(G.effective_walk_s(p, 3.0, 8.0), 1.0 if (6 / 5 + 5 / 80) < 1.0 else 6 / 5 + 5 / 80)

    def test_probe_points_cover_vertices_centres_and_both_sides_of_the_diagonal(self):
        w = W(); pts = G.probe_points(w, copy.deepcopy(prof()["player"]["start"]))
        self.assertEqual(len(pts), 64)
        self.assertEqual(sum(q[3] for q in pts), 16)
        self.assertEqual(G.probe_points(W(h=-5.0), copy.deepcopy(prof()["player"]["start"])), [])

    def test_image_checks(self):
        from PIL import Image
        d = tempfile.mkdtemp(); rng = np.random.default_rng(1)
        def save(n, a): Image.fromarray((a * 255).astype(np.uint8)).save(d + "/" + n)
        noise = rng.uniform(0.2, 0.8, (36, 64, 3)); other = rng.uniform(0.2, 0.8, (36, 64, 3))
        save("a.png", noise); save("b.png", other); save("same.png", noise); save("flat.png", np.full((36, 64, 3), 0.5)); save("black.png", np.zeros((36, 64, 3)))
        self.assertEqual(G.image_checks(d + "/a.png", d + "/b.png")[0], [])
        self.assertTrue(any("differ" in f for f in G.image_checks(d + "/a.png", d + "/same.png")[0]))
        self.assertTrue(any("blank or crushed" in f for f in G.image_checks(d + "/flat.png", d + "/b.png")[0]))
        self.assertTrue(any("blank or crushed" in f for f in G.image_checks(d + "/a.png", d + "/black.png")[0]))

    def test_stamps_flip_when_any_hashed_input_changes(self):
        d = tempfile.mkdtemp(); wd = os.path.join(d, "gg_data", "world"); lv = os.path.join(d, "levels", "main"); os.makedirs(wd); os.makedirs(lv)
        os.makedirs(os.path.join(d, "addons", "gg"))
        for n in ("terrain", "colliders", "player", "level", "scatter"): open(os.path.join(lv, n + ".tscn"), "w").write(n)
        open(wd + "/start.json", "w").write("{}"); open(wd + "/water_dist.f32", "w").write("w"); open(d + "/addons/gg/runtime.lock.json", "w").write("{}")
        open(d + "/project.godot", "w").write("[input]\nmove_forward={a}\n[rendering]\nx=1\n")
        p = prof()
        S.atomic_json(wd + "/player_ok.json", {"heights_sha": "H", "hashes": G.player_hashes(d, p)})
        self.assertEqual(G.stamp_state(d, p, "player_ok.json", "H"), (True, []))
        self.assertEqual(G.stamp_state(d, p, "player_ok.json", "other")[0], False)
        self.assertEqual(G.stamp_state(d, p, "smoke_ok.json", "H")[0], False)
        for rel, new, key in (("/levels/main/terrain.tscn", "x", "terrain_scene"), ("/levels/main/colliders.tscn", "x", "colliders_scene"), ("/levels/main/player.tscn", "x", "player_scene"),
                              ("/levels/main/level.tscn", "x", "level_scene"), ("/gg_data/world/start.json", "x", "start_json"), ("/gg_data/world/water_dist.f32", "x", "water_dist"),
                              ("/levels/main/scatter.tscn", "x", "scatter_scene"), ("/addons/gg/runtime.lock.json", "x", "runtime_lock"), ("/project.godot", "[input]\nmove_forward={b}\n[rendering]\nx=1\n", "project_input")):
            old = open(d + rel).read(); open(d + rel, "w").write(new)
            ok, changed = G.stamp_state(d, p, "player_ok.json", "H")
            self.assertFalse(ok, rel); self.assertEqual(changed, [key], rel)
            open(d + rel, "w").write(old)
        open(d + "/project.godot", "a").write("y=2\n")                      # a change outside [input] is not an input change
        self.assertTrue(G.stamp_state(d, p, "player_ok.json", "H")[0])
        p2 = copy.deepcopy(p); p2["camera"]["fov_deg"] = 90.0
        self.assertEqual(G.stamp_state(d, p2, "player_ok.json", "H")[1], ["profile_player_camera"])

    def test_solids_from_scatter_categories_and_cap(self):
        d = tempfile.mkdtemp(); os.makedirs(d + "/gg_data/scatter")
        fams = {"pine": {"instances": [[1, 2, 3, 0, 1.0], [4, 5, 6, 0, 2.0]]}, "grass": {"instances": [[1, 1, 1, 0, 1.0]]}, "rock": {"instances": [[7, 8, 9, 0, 1.0]]}}
        json.dump({"families": fams}, open(d + "/gg_data/scatter/main.json", "w"))
        cat = {"families": {"pine": {"category": "tree_upland"}, "grass": {"category": "grass"}, "rock": {"category": "rock"}}}
        shapes, solids, counts = G.solids_from_scatter(d, "main", cat)
        self.assertEqual(counts, {"pine": 2, "rock": 1}); self.assertEqual([s[0] for s in shapes], ["cyl", "cyl", "box"])
        self.assertAlmostEqual(shapes[1][4], 0.6)           # trunk radius 0.3 x scale 2
        fams["pine"]["instances"] = [[0, 0, 0, 0, 1.0]] * (G.MAX_SOLIDS + 1)
        json.dump({"families": fams}, open(d + "/gg_data/scatter/main.json", "w"))
        with self.assertRaises(gg_godot.Refused) as c: G.solids_from_scatter(d, "main", cat)
        self.assertIn("pine", str(c.exception))
        self.assertEqual(G.solids_from_scatter(tempfile.mkdtemp(), "main", cat), ([], [], {}))


class InitRunway(unittest.TestCase):
    def run_init(self, runway):
        from unittest import mock
        written = {}
        base = {"dimension": "3d", "view": "third_person", "world": {"size_m": [256.0, 256.0]}, "level": "main", "style": {"preset": "low-poly"}}
        with mock.patch.object(G.gg_project, "load_profile", return_value=dict(base)), mock.patch.object(G, "_write_profile", side_effect=lambda proj, prof: written.update(prof)):
            code = G.init("/p", runway_m=runway)
        return code, written

    def test_default_runway_is_unchanged(self):
        self.assertEqual(self.run_init(None)[1]["player"]["start"]["runway_m"], 20.0)

    def test_runway_option_sets_the_start_rule(self):
        code, w = self.run_init(12)
        self.assertEqual((code, w["player"]["start"]["runway_m"]), (0, 12.0))

    def test_too_short_runway_is_refused_by_the_existing_validation(self):
        with self.assertRaises(G.Refused):
            self.run_init(1)


if __name__ == "__main__":
    unittest.main()
