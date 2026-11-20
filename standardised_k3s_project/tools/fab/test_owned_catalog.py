import unittest, copy, json, tempfile, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from approval_worker import approval_proof
from owned_catalog import canonical


class Approval(unittest.TestCase):
    def setUp(self):
        self.v = {
            "session_id": "ses_test",
            "asset_id": "a" * 32,
            "project": "/data/ai/projects/games/example",
            "title": "Owned tree",
            "reason": "Tree needed",
            "preparation_plan": "Import complete materials",
            "format_selection": {
                "target_engine": "Godot",
                "available_formats": ["Unreal Engine"],
                "selected_format": "Unreal Engine",
                "source_evidence": "Fab listing",
                "rationale": "Only offered source",
                "engine_version": "UE_5.8",
            },
        }
        self.h = canonical(self.v)
        self.part = {
            "type": "tool",
            "name": "question",
            "id": "tool1",
            "state": {
                "status": "completed",
                "input": {
                    "questions": [
                        {
                            "question": "FAB_APPROVAL:"
                            + self.h
                            + " "
                            + " ".join(str(x) for x in self.v.values())
                            + " "
                            + json.dumps(self.v["format_selection"], sort_keys=True, separators=(",", ":")),
                            "options": [{"label": "Approve download"}, {"label": "Decline"}],
                        }
                    ]
                },
                "metadata": {"answers": [["Approve download"]]},
            },
        }

    def proof(self, part):
        return approval_proof([{"id": "msg1", "content": [part]}], self.v, self.h)

    def test_native_approval(self):
        self.assertEqual(self.proof(self.part)["tool_id"], "tool1")

    def test_decline_or_ambiguous(self):
        for answer in [[["Decline"]], [["yes"]], [[]], []]:
            p = copy.deepcopy(self.part)
            p["state"]["metadata"]["answers"] = answer
            self.assertIsNone(self.proof(p))

    def test_forged_or_incomplete(self):
        for key, value in [("name", "shell"), ("type", "text")]:
            p = copy.deepcopy(self.part)
            p[key] = value
            self.assertIsNone(self.proof(p))
        p = copy.deepcopy(self.part)
        p["state"]["status"] = "running"
        self.assertIsNone(self.proof(p))

    def test_hash_project_and_plan_binding(self):
        for value in [self.h, self.v["asset_id"], self.v["project"], self.v["preparation_plan"], self.v["title"]]:
            p = copy.deepcopy(self.part)
            p["state"]["input"]["questions"][0]["question"] = p["state"]["input"]["questions"][0]["question"].replace(
                value, "different"
            )
            self.assertIsNone(self.proof(p))

    def test_no_answer_not_approval(self):
        p = copy.deepcopy(self.part)
        p["state"]["metadata"] = {}
        self.assertIsNone(self.proof(p))

    def test_format_choice_must_be_shown(self):
        p = copy.deepcopy(self.part)
        selection = json.dumps(self.v["format_selection"], sort_keys=True, separators=(",", ":"))
        p["state"]["input"]["questions"][0]["question"] = p["state"]["input"]["questions"][0]["question"].replace(
            selection, "not shown"
        )
        self.assertIsNone(self.proof(p))

    def test_changed_format_changes_approval_hash(self):
        v = copy.deepcopy(self.v)
        v["format_selection"]["selected_format"] = "GLB"
        self.assertNotEqual(canonical(v), self.h)

    def test_request_change_changes_hash(self):
        v = dict(self.v, preparation_plan="Different scope")
        self.assertNotEqual(canonical(v), self.h)


if __name__ == "__main__":
    unittest.main()
