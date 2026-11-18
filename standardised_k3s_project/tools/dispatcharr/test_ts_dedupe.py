import io, unittest
import ts_dedupe as t

VPID, APID, PMT = 0x100, 0x101, 0x1000


def pkt(pid, payload, pusi=False, rai=False, cc=0):
    af = b""
    if rai:
        af = bytes([1, 0x40])
        afc = 3
    else:
        afc = 1
    body = af + payload
    body = body + b"\xff" * (184 - len(body))
    return bytes([0x47, (0x40 if pusi else 0) | (pid >> 8), pid & 0xFF, (afc << 4) | cc]) + body[:184]


def pes(sid, pts, extra=b"\x00\x00\x01\x65"):
    p = bytes([0x21 | ((pts >> 29) & 0x0E), (pts >> 22) & 0xFF, 0x01 | ((pts >> 14) & 0xFE), (pts >> 7) & 0xFF, 0x01 | ((pts << 1) & 0xFE)])
    return b"\x00\x00\x01" + bytes([sid]) + b"\x00\x00\x80\x80\x05" + p + extra


def pat():
    sec = bytes([0, 0xB0, 13, 0, 1, 0xC1, 0, 0, 0, 1, 0xE0 | (PMT >> 8), PMT & 0xFF]) + b"\0\0\0\0"
    return pkt(0, b"\x00" + sec, pusi=True)


def pmt():
    sec = bytes([2, 0xB0, 23, 0, 1, 0xC1, 0, 0, 0xE1, 0x00, 0xF0, 0,
                 0x1B, 0xE0 | (VPID >> 8), VPID & 0xFF, 0xF0, 0, 0x0F, 0xE0 | (APID >> 8), APID & 0xFF, 0xF0, 0]) + b"\0\0\0\0"
    return pkt(PMT, b"\x00" + sec, pusi=True)


def connection(start_s, end_s):
    """A fake provider connection covering [start_s, end_s) of the live timeline, 25 fps, keyframe each second."""
    out = [pat(), pmt()]
    for n in range(int(start_s * 25), int(end_s * 25)):
        pts = 90000 * n // 25
        out.append(pkt(VPID, pes(0xE0, pts), pusi=True, rai=(n % 25 == 0)))
        if n % 2 == 0:
            out.append(pkt(APID, pes(0xC0, pts), pusi=True))
    return out


def delivered_video_pts(data):
    res = []
    for i in range(0, len(data), 188):
        p = data[i:i + 188]
        if ((p[1] & 0x1F) << 8 | p[2]) == VPID and p[1] & 0x40:
            res.append(t.parse_pts(p))
    return res


class Tests(unittest.TestCase):
    def test_replayed_part_dropped_and_stream_continuous(self):
        out = io.BytesIO()
        r = t.Relay(out)
        r.new_connection()
        for p in connection(0, 12):
            r.feed(p)
        r.new_connection()                       # provider restarts 6 s earlier and re-sends
        for p in connection(6, 20):
            r.feed(p)
        pts = delivered_video_pts(out.getvalue())
        self.assertEqual(pts, sorted(set(pts)))            # strictly increasing: nothing repeated
        self.assertEqual(len(pts), 20 * 25)                # nothing lost: every frame exactly once
        self.assertEqual(pts[0], 0)

    def test_first_connection_passes_everything(self):
        out = io.BytesIO()
        r = t.Relay(out)
        r.new_connection()
        for p in connection(0, 3):
            r.feed(p)
        self.assertEqual(len(delivered_video_pts(out.getvalue())), 75)

    def test_continuity_counters_stay_sequential(self):
        out = io.BytesIO()
        r = t.Relay(out)
        r.new_connection()
        for p in connection(0, 6):
            r.feed(p)
        r.new_connection()
        for p in connection(3, 9):
            r.feed(p)
        data = out.getvalue()
        last = {}
        for i in range(0, len(data), 188):
            p = data[i:i + 188]
            pid = (p[1] & 0x1F) << 8 | p[2]
            if (p[3] >> 4) & 1:
                if pid in last:
                    self.assertEqual(p[3] & 15, (last[pid] + 1) & 15)
                last[pid] = p[3] & 15

    def test_waits_for_keyframe_after_reconnect(self):
        out = io.BytesIO()
        r = t.Relay(out)
        r.new_connection()
        for p in connection(0, 4):
            r.feed(p)
        r.new_connection()
        # a connection whose frames resume mid-second: only whole GOPs after the last delivered PTS may appear
        for p in connection(3.5, 8):
            r.feed(p)
        pts = delivered_video_pts(out.getvalue())
        self.assertEqual(pts, sorted(set(pts)))
        self.assertEqual(pts[100] , 90000 * 4)             # resumes exactly at the first keyframe after the overlap


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def timed_connection(start_s, end_s, shift=0):
    """Like connection(), but each packet carries the second (on the live timeline) it is delivered at."""
    out = [(start_s, pat()), (start_s, pmt())]
    for n in range(int(start_s * 25), int(end_s * 25)):
        pts = (90000 * n // 25 + shift) % t.PTS_MOD
        out.append((n / 25.0, pkt(VPID, pes(0xE0, pts), pusi=True, rai=(n % 25 == 0))))
        if n % 2 == 0:
            out.append((n / 25.0, pkt(APID, pes(0xC0, pts), pusi=True)))
    return out


def live_plan(connections, reconnect_s):
    """connections: [(start_s, end_s, shift)] delivered in real time; the next one starts reconnect_s after the previous ended."""
    plan, wall = [], 0.0
    for start, end, shift in connections:
        plan.append((wall, None))
        plan += [(wall + (ts - start), p) for ts, p in timed_connection(start, end, shift)]
        wall += (end - start) + reconnect_s
    return sorted(plan, key=lambda x: x[0])


def simulate(delay, plan, step=0.02):
    """Feed plan [(wall seconds, packet or None=new connection)] through Relay+Pacer; return the wall times video frames came out."""
    clock = Clock()
    pacer = t.Pacer(io.BytesIO(), delay, now=clock)
    relay = t.Relay(pacer)
    released, i = [], 0
    end = plan[-1][0] + delay + 5
    while clock.t <= end:
        while i < len(plan) and plan[i][0] <= clock.t:
            relay.new_connection() if plan[i][1] is None else relay.feed(plan[i][1])
            i += 1
        released += [clock.t for pk in pacer.due(clock.t) if ((pk[1] & 0x1F) << 8 | pk[2]) == VPID and pk[1] & 0x40]
        clock.t += step
    return released


class PacerTests(unittest.TestCase):
    CUT = [(0, 30, 0), (5, 80, 0)]  # live 0-30 s, cut, reconnect after 4 s; the new connection restarts 25 s earlier and is re-sent in real time

    def max_gap(self, released):
        return max(b - a for a, b in zip(released, released[1:]))

    def test_provider_cut_is_a_visible_stall_without_a_buffer(self):
        self.assertGreater(self.max_gap(simulate(0.0001, live_plan(self.CUT, 4))), 20)

    def test_buffer_longer_than_the_blind_period_hides_the_cut(self):
        released = simulate(32, live_plan(self.CUT, 4))
        self.assertLess(self.max_gap(released), 0.5)
        self.assertEqual(len(released), 80 * 25)             # every frame exactly once

    def test_shorter_buffer_still_stalls(self):
        self.assertGreater(self.max_gap(simulate(20, live_plan(self.CUT, 4))), 3)

    def test_release_is_delayed_by_exactly_the_buffer(self):
        released = simulate(10, live_plan([(0, 12, 0)], 0))
        self.assertAlmostEqual(released[0], 10, delta=0.05)
        self.assertAlmostEqual(released[-1], 10 + 11.96, delta=0.1)

    def test_pts_jump_re_anchors_instead_of_waiting(self):
        released = simulate(3, live_plan([(0, 5, 0), (0, 5, 40000 * 90000)], 0))
        self.assertLess(released[-1], 5 + 5 + 3 + 1)         # nowhere near 40,000 s
        self.assertLess(self.max_gap(released), 1)

    def test_pts_wraparound_is_continuous(self):
        clock = Clock()
        pacer = t.Pacer(io.BytesIO(), 2, now=clock)
        release = [pacer._stamp(pkt(VPID, pes(0xE0, (t.PTS_MOD - 3 * 90000 + 90000 * n // 25) % t.PTS_MOD), pusi=True), 0.0) for n in range(6 * 25)]
        self.assertTrue(all(abs(b - a - 0.04) < 1e-6 for a, b in zip(release, release[1:])))

    def test_keepalive_null_packets_flow_before_the_first_packet_is_due(self):
        import time as _t
        sink = io.BytesIO()
        pacer = t.Pacer(sink, 5).start()                     # real clock
        pacer.write(pat())
        _t.sleep(0.7)
        data = sink.getvalue()
        self.assertGreater(len(data), 0)
        self.assertTrue(all(data[i:i + 188] == t.NULL_PACKET for i in range(0, len(data), 188)))

    def test_closed_pipe_raises_in_the_writer(self):
        class Broken:
            def write(self, b):
                raise BrokenPipeError()

            def flush(self):
                pass
        import time as _t
        pacer = t.Pacer(Broken(), 0.01).start()
        pacer.write(pat())
        _t.sleep(0.5)
        with self.assertRaises(BrokenPipeError):
            pacer.write(pat())


class FakeSource:
    def __init__(self, started):
        self.started, self.got_data, self.closed = started, False, False

    def close(self):
        self.closed = True


class ControllerTests(unittest.TestCase):
    def make(self, standby_after=10, cap=48 << 20):
        self.clock = Clock()
        self.opened = []

        def opener():
            src = FakeSource(self.clock.t)
            self.opened.append(src)
            return src

        self.relay = t.Relay(io.BytesIO())
        self.ctl = t.Controller(self.relay, opener, now=self.clock, sleep=lambda s: None, standby_after=standby_after, cap_bytes=cap)
        self.ctl.start()
        self.buffered_at_switch = None
        original = self.ctl.on_end

        def spy(src, err):
            if src is self.ctl.active and self.ctl.standby is not None:
                self.buffered_at_switch = len(self.ctl.sbuf)
            original(src, err)
        self.ctl.on_end = spy

    def run_events(self, events):
        """events: [(wall, priority, fn)]; run in order, setting the clock."""
        for wall, _, fn in sorted(events, key=lambda e: (e[0], e[1])):
            self.clock.t = wall
            fn()

    def scenario(self, a_end_wall, a_frames_until):
        """Live timeline starts at 40 s. A is the first connection (real time). A standby opens at wall 10, is restarted 25 s behind live and
        catches up in a burst, then runs in real time. A is cut at a_end_wall."""
        ev = []
        a = self.opened[0]
        for ts, p in timed_connection(40, a_frames_until):
            ev.append((ts - 40, 1, lambda p=p: self.ctl.on_data(a, [p])))
        for w in range(0, 90):
            ev.append((w, 0, self.ctl.tick))
        ev.append((a_end_wall, 2, lambda: self.ctl.on_end(a, None)))
        for ts, p in timed_connection(25, 100):
            wall = 10 if ts < 50 else ts - 40
            ev.append((wall, 1.5, lambda p=p: self.ctl.on_data(self.opened[1], [p])))
        self.run_events(ev)
        return delivered_video_pts(self.relay.out.getvalue())

    def test_cut_on_a_keyframe_switches_with_no_loss_and_no_repeat(self):
        self.make()
        pts = self.scenario(30, 70)
        self.assertEqual(pts, sorted(set(pts)))
        self.assertEqual(pts[0], 40 * 90000)
        self.assertEqual(len(pts), 60 * 25)                  # live 40 s -> 100 s, every frame exactly once
        self.assertIs(self.ctl.active, self.opened[1])
        self.assertEqual(len(self.opened), 3)                # and the next standby is already open
        self.assertGreater(self.buffered_at_switch, 400)     # it switched with ~20 s of real data in hand, not at the last moment

    def test_cut_mid_gop_loses_at_most_one_gop(self):
        self.make()
        pts = self.scenario(30.5, 70.5)
        self.assertEqual(pts, sorted(set(pts)))
        self.assertGreaterEqual(len(pts), 60 * 25 - 25)

    def test_without_a_standby_it_reconnects_like_before(self):
        self.make(standby_after=0)
        a = self.opened[0]
        for ts, p in timed_connection(0, 3):
            self.ctl.on_data(a, [p])
        self.ctl.on_end(a, None)
        self.assertEqual(len(self.opened), 2)
        self.assertIs(self.ctl.active, self.opened[1])
        self.assertTrue(a.closed)

    def test_refused_standby_backs_off_and_does_not_hammer(self):
        self.make()
        self.clock.t = 10
        self.ctl.tick()
        b = self.opened[1]
        self.ctl.on_end(b, IOError("HTTP 509"))              # nothing received: refused
        self.assertEqual(len(self.opened), 2)
        self.clock.t = 15
        self.ctl.tick()
        self.assertEqual(len(self.opened), 2)                # still blocked
        self.clock.t = 21
        self.ctl.tick()
        self.assertEqual(len(self.opened), 3)
        self.ctl.on_end(self.opened[2], IOError("HTTP 509"))
        self.assertEqual(self.ctl.block_for, 20.0)           # doubled again

    def test_standby_buffer_over_the_cap_is_dropped(self):
        self.make(cap=188 * 10)
        a = self.opened[0]
        for ts, p in timed_connection(40, 41):
            self.ctl.on_data(a, [p])
        self.clock.t = 10
        self.ctl.tick()
        b = self.opened[1]
        for ts, p in timed_connection(41, 44):
            self.ctl.on_data(b, [p])
        self.assertIsNone(self.ctl.standby)
        self.assertTrue(b.closed)

    def test_events_from_connections_already_closed_are_ignored(self):
        self.make(standby_after=0)
        stale = FakeSource(0)
        before = self.relay.out.getvalue()
        self.ctl.on_data(stale, [pat()])
        self.ctl.on_end(stale, IOError("late"))
        self.assertEqual(len(self.opened), 1)
        self.assertEqual(self.relay.out.getvalue(), before)

    def test_aligner_realigns_after_lost_sync(self):
        good = b"".join(p for _, p in timed_connection(0, 1))
        al = t.Aligner()
        pk = al.feed(b"\x01\x02\x03" + good)
        self.assertTrue(pk and all(x[0] == 0x47 for x in pk))
        self.assertTrue(all(len(x) == 188 and x[0] == 0x47 for x in al.feed(good)))
        al2 = t.Aligner()
        self.assertEqual(len(al2.feed(good[:100])), 0)        # a partial packet waits for the rest
        self.assertEqual(len(al2.feed(good[100:188])), 1)


if __name__ == "__main__":
    unittest.main()
