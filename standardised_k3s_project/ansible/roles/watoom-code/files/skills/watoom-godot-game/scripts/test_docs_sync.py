"""Skill docs == language-knowledge sources, every card span exists, every script named in a card exists."""
import json, os, re, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_manual as sm

MAN = os.path.join(sm.LK, "manuals", "watoom-godot-game")


@unittest.skipUnless(os.path.isdir(MAN), "language-knowledge manuals not present")
class T(unittest.TestCase):
    def test_sources_identical(self):
        self.assertEqual(sm.drift(), [], "run scripts/sync_manual.py")

    def test_cards(self):
        norm = lambda s: " ".join(s.split())
        n = 0
        for line in open(os.path.join(MAN, "entries.jsonl")):
            if not line.strip():
                continue
            e = json.loads(line); n += 1
            src = norm(open(os.path.join(MAN, "sources", e["source_file"])).read())
            self.assertIn(norm(e["source_span"]), src, e["symbol"])
            for script in re.findall(r"gg_[a-z_]+\.py", e["signature"] + e["summary"]):
                self.assertTrue(os.path.exists(os.path.join(sm.HERE, script)), "%s names missing %s" % (e["symbol"], script))
        self.assertGreater(n, 0)


if __name__ == "__main__":
    unittest.main()
