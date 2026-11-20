import unittest
from optimise import qualified


class Qualification(unittest.TestCase):
    def state(self):
        return {
            "skills": {"s": {"baselineTests": {"cases": [1]}, "baseline": "b", "sourceChanged": False}},
            "revisions": {"r": {"skill": "s", "state": "evaluated", "previous": "b"}},
            "comparisons": {
                "r": {
                    "measurementOrigin": "observed",
                    "cases": [{"original": {"tokens": 100}, "candidate": {"tokens": 90}}],
                    "measurementProtocol": {
                        "registeredSuite": "fixed-v1",
                        "domainRepresentative": True,
                        "pairedRepetitions": 3,
                        "sameEnvironment": True,
                        "regressionChecks": True,
                        "verifierReceipts": ["one", "two", "three"],
                    },
                }
            },
        }

    def test_registered_repeated_comparison(self):
        self.assertTrue(qualified(self.state(), "r"))

    def test_single_noisy_replay_blocked(self):
        s = self.state()
        s["comparisons"]["r"]["measurementProtocol"]["pairedRepetitions"] = 1
        self.assertFalse(qualified(s, "r"))

    def test_changed_source_or_untested_candidate_blocked(self):
        s = self.state()
        s["skills"]["s"]["sourceChanged"] = True
        self.assertFalse(qualified(s, "r"))
        s = self.state()
        s["revisions"]["r"]["state"] = "candidate"
        self.assertFalse(qualified(s, "r"))

    def test_unregistered_or_regressed_suite_blocked(self):
        for field in ["registeredSuite", "sameEnvironment", "regressionChecks", "verifierReceipts"]:
            s = self.state()
            s["comparisons"]["r"]["measurementProtocol"][field] = False
            self.assertFalse(qualified(s, "r"))


class IndependentAuthority(unittest.TestCase):
    def test_app_metadata_alone_cannot_authorise_promotion(self):
        import tempfile, pathlib
        from optimise import verified_comparison

        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(verified_comparison(pathlib.Path(d), {"scope": {"project": "p"}}, "unproven"))
