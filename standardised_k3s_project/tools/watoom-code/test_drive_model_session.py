import json, os, tempfile, unittest
import drive_model_session as D


def msg(*parts):
    return {'type': 'assistant', 'content': list(parts)}


tool = lambda n: {'type': 'tool', 'name': n}
text = lambda t: {'type': 'text', 'text': t}


class Summarise(unittest.TestCase):
    def test_stall_is_a_blocked_report_with_no_tool_call_in_the_last_turn(self):
        stalled = D.summarise([msg(text('{"result": "BLOCKED", "blocker": "x"}')), msg(tool('read'), tool('write'))])
        self.assertTrue(stalled['stalled']); self.assertEqual(stalled['tools'], {'read': 1, 'write': 1})
        spaced = D.summarise([msg(text('{"result":\n\n "BLOCKED",\n "blocker":"x"}'))])
        self.assertTrue(spaced['stalled'])

    def test_a_normal_turn_or_a_blocked_report_after_tool_calls_is_not_a_stall(self):
        self.assertFalse(D.summarise([msg(tool('shell'), text('{"result":"BLOCKED"}'))])['stalled'])
        self.assertFalse(D.summarise([msg(tool('shell'), text('all done'))])['stalled'])
        self.assertFalse(D.summarise([])['stalled'])

    def test_job_statuses_newest_first(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(d + '/.opencode/worker-requests')
            for i, (job, st) in enumerate([('a', 'FAILED'), ('b', 'PASS')]):
                f = '%s/.opencode/worker-requests/%064d.status.json' % (d, i)
                json.dump({'job': job, 'status': st, 'reason': 'r'}, open(f, 'w')); os.utime(f, (100 + i, 100 + i))
            self.assertEqual([j for j, _, _ in D.job_statuses(d)], ['b', 'a'])


if __name__ == '__main__':
    unittest.main()
