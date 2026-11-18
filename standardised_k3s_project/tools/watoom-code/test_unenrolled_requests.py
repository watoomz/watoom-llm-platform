import json, pathlib, tempfile, unittest
import game_worker_bridge as B


class Unenrolled(unittest.TestCase):
    def test_unenrolled_request_gets_a_failed_status_once(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d) / 'games'; priv = pathlib.Path(d) / 'private'; priv.mkdir()
            B.PRIVATE = priv
            good = root / 'enrolled'; bad = root / 'stranger'
            ids = {}
            for p in (good, bad):
                (p / '.opencode/worker-requests').mkdir(parents=True)
                v = {'schema': 1, 'project': str(p), 'operation': 'godot-game', 'job': 'j', 'source_fingerprint': 'a' * 64, 'session_id': 's', 'message_id': 'm', 'call_id': 'c', 'agent': 'watoom-builder', 'created_at': 1}
                v['request_id'] = B.request_identity(v); ids[p.name] = v['request_id']
                (p / '.opencode/worker-requests' / (v['request_id'] + '.json')).write_text(json.dumps(v))
            self.assertEqual(B.reject_unenrolled({'projects': [str(good)]}, root), [ids['stranger']])
            st = json.loads((bad / '.opencode/worker-requests' / (ids['stranger'] + '.status.json')).read_text())
            self.assertEqual((st['status'], st['failure_code']), ('FAILED', 'project_not_enrolled'))
            self.assertIn('watoom_game_worker_extra_projects', st['reason'])
            self.assertFalse((good / '.opencode/worker-requests' / (ids['enrolled'] + '.status.json')).exists())
            self.assertEqual(B.reject_unenrolled({'projects': [str(good)]}, root), [])   # already answered


if __name__ == '__main__':
    unittest.main()
