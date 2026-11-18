#!/usr/bin/env python3
"""Seamless live MPEG-TS relay for providers that cap a connection (for example every 120 s) and restart each new
connection about 25 s earlier on the live timeline.

Plain reconnecting (ffmpeg -reconnect_at_eof, or Dispatcharr's own retry) replays those ~25 s at every cut, so the
viewer sees a rewind and the stream drifts further behind live each time. This relay reconnects itself and, after a
reconnect, drops every packet until the video timeline passes the last frame already delivered (and a keyframe is
reached), so the output is one continuous stream with no repeat and no gap beyond the reconnect time.

Usage: ts_dedupe.py URL [USER_AGENT]       writes MPEG-TS to stdout, runs until stdout closes or it is killed.
Used as the command of a Dispatcharr stream profile; standard library plus requests (already in the image).
"""
import os
import queue
import sys
import threading
import time

PKT = 188
PTS_MOD = 1 << 33


def parse_pts(pkt):
    """PTS (90 kHz) of the PES that starts in this packet, or None. Also returns the payload start offset."""
    afc = (pkt[3] >> 4) & 3
    off = 4
    if afc & 2:
        off += 1 + pkt[4]
    if not (afc & 1) or off + 14 > PKT:
        return None
    if pkt[off:off + 3] != b"\x00\x00\x01":
        return None
    if not (pkt[off + 7] & 0x80):
        return None
    p = pkt[off + 9:off + 14]
    return ((p[0] >> 1) & 7) << 30 | p[1] << 22 | (p[2] >> 1) << 15 | p[3] << 7 | p[4] >> 1


def stream_kind(pkt):
    """'v' or 'a' for the PES that starts in this packet, else None."""
    afc = (pkt[3] >> 4) & 3
    off = 4 + (1 + pkt[4] if afc & 2 else 0)
    if not (afc & 1) or pkt[off:off + 3] != b"\x00\x00\x01":
        return None
    sid = pkt[off + 3]
    return "v" if 0xE0 <= sid <= 0xEF else ("a" if 0xC0 <= sid <= 0xDF or sid == 0xBD else None)


def is_keyframe(pkt):
    """Random-access flag set, or an IDR NAL (H.264 type 5 / HEVC IRAP) near the start of the payload."""
    afc = (pkt[3] >> 4) & 3
    if afc & 2 and pkt[4] and pkt[5] & 0x40:
        return True
    off = 4 + (1 + pkt[4] if afc & 2 else 0)
    body = pkt[off:]
    i = 0
    while True:
        i = body.find(b"\x00\x00\x01", i)
        if i < 0 or i + 4 >= len(body):
            return False
        nal = body[i + 3]
        if (nal & 0x1F) == 5 or 16 <= ((nal >> 1) & 0x3F) <= 21:
            return True
        i += 3


class Relay:
    def __init__(self, out):
        self.out = out
        self.last_v = None          # last video PTS delivered
        self.last_a = None          # last audio PTS delivered
        self.cc = {}                # output continuity counter per PID
        self.tables = {}            # latest PAT/PMT packets (PID -> packet)
        self.pmt_pids = set()
        self.audio_pids = set()
        self.gate = True            # True while delivering; False while skipping the replayed part
        self.audio_wait = False     # after the gate opens, drop audio until a whole PES starts
        self.drop_audio = False     # current audio PES is a replay

    @staticmethod
    def ahead(new, last):
        return last is None or 0 < ((new - last) % PTS_MOD) < (PTS_MOD >> 1)

    @staticmethod
    def caught_up(new, last, tolerance):
        """True when `new` is no more than `tolerance` ticks behind `last` (or ahead of it)."""
        if last is None:
            return True
        d = (new - last) % PTS_MOD
        return (d if d < (PTS_MOD >> 1) else d - PTS_MOD) > -tolerance

    def new_connection(self):
        self.gate = self.last_v is None
        self.audio_wait = False
        self.drop_audio = False

    def emit(self, pkt):
        pid = ((pkt[1] & 0x1F) << 8) | pkt[2]
        pkt = bytearray(pkt)
        if (pkt[3] >> 4) & 1:  # has payload: advance this PID's counter
            self.cc[pid] = (self.cc.get(pid, -1) + 1) & 15
        pkt[3] = (pkt[3] & 0xF0) | (self.cc.get(pid, 0) & 15)
        self.out.write(pkt)

    def feed(self, pkt):
        if pkt[0] != 0x47:
            return
        pid = ((pkt[1] & 0x1F) << 8) | pkt[2]
        if pid == 0x1FFF:
            return
        pusi = bool(pkt[1] & 0x40)
        if pid == 0 or pid in self.pmt_pids:
            self.tables[pid] = pkt
            if pid == 0 and pusi:
                self.pmt_pids = self._pmt_pids(pkt)
            if self.gate:
                self.emit(pkt)
            return
        kind = stream_kind(pkt) if pusi else None
        if kind == "a":
            self.audio_pids.add(pid)
        if not self.gate:
            if kind != "v":
                return
            pts = parse_pts(pkt)
            if pts is None or not self.ahead(pts, self.last_v) or not is_keyframe(pkt):
                return
            self.gate = True
            self.audio_wait = True
            for t in list(self.tables.values()):
                self.emit(t)
        if pid in self.audio_pids:
            if kind == "a":
                self.audio_wait = False
                pts = parse_pts(pkt)
                if pts is not None:
                    if self.last_a is not None and not self.ahead(pts, self.last_a):
                        self.drop_audio = True
                        return
                    self.last_a = pts
                self.drop_audio = False
            elif self.audio_wait or self.drop_audio:
                return
        elif kind == "v":
            pts = parse_pts(pkt)
            if pts is not None and self.ahead(pts, self.last_v):
                self.last_v = pts
        self.emit(pkt)

    @staticmethod
    def _pmt_pids(pkt):
        afc = (pkt[3] >> 4) & 3
        off = 4 + (1 + pkt[4] if afc & 2 else 0)
        off += 1 + pkt[off]
        section_len = ((pkt[off + 1] & 0x0F) << 8) | pkt[off + 2]
        end = min(off + 3 + section_len - 4, PKT)
        pids = set()
        i = off + 8
        while i + 4 <= end:
            if (pkt[i] << 8 | pkt[i + 1]) != 0:
                pids.add(((pkt[i + 2] & 0x1F) << 8) | pkt[i + 3])
            i += 4
        return pids


NULL_PACKET = bytes([0x47, 0x1F, 0xFF, 0x10]) + b"\xff" * 184


class Pacer:
    """Time-shift the output by `delay` seconds so a provider cut is invisible to the viewer.

    After every cut the relay is blind for about 29 s (reconnect plus dropping the ~25 s replay at the provider's real-time
    pace). Output that runs `delay` seconds behind what has been received rides through that gap on its backlog. The release
    time of each packet comes from the stream's own clock (video/audio PTS), not from when it arrived, so a gap in arrival is
    not copied into the output. A jump or reset of the PTS clock re-anchors instead of waiting it out. Until the first packet is
    due, NULL packets keep bytes flowing so the caller does not decide the stream never started.
    """
    JUMP = 10 * 90000   # a PTS step bigger than this (either way) is a discontinuity, not time passing

    def __init__(self, out, delay=35.0, now=time.monotonic):
        import collections
        import threading
        self.out, self.delay, self.now = out, float(delay), now
        self.q = collections.deque()      # (release time, packet)
        self.cv = threading.Condition()
        self.err = None
        self.anchor = None                # wall time that media position `media0` is released at
        self.media = self.media0 = 0.0    # media clock in seconds, unwrapped
        self.last_pts = None
        self.last_release = 0.0
        self.started = False
        self.thread = None

    def _stamp(self, pkt, t):
        if self.anchor is None:
            self.anchor = t + self.delay
        pts = parse_pts(pkt) if (pkt[1] & 0x40) and stream_kind(pkt) else None
        if pts is not None:
            if self.last_pts is None:
                self.media = self.media0 = 0.0
            else:
                d = (pts - self.last_pts) % PTS_MOD
                step = d if d < (PTS_MOD >> 1) else d - PTS_MOD       # signed distance in 90 kHz ticks
                if abs(step) > self.JUMP:                              # discontinuity: continue right after the last packet
                    self.anchor, self.media0 = self.last_release, self.media
                elif step > 0:
                    self.media += step / 90000.0
                else:
                    pts = self.last_pts                                # small reorder: keep the running maximum
            self.last_pts = pts
        release = max(self.anchor + (self.media - self.media0), self.last_release)
        self.last_release = release
        return release

    def write(self, pkt):
        with self.cv:
            if self.err:
                raise BrokenPipeError(str(self.err))
            self.q.append((self._stamp(pkt, self.now()), bytes(pkt)))
            self.cv.notify()

    def flush(self):
        pass

    def due(self, t, limit=500):
        """Packets whose release time has come (pure; the thread calls it)."""
        out = []
        while self.q and self.q[0][0] <= t and len(out) < limit:
            out.append(self.q.popleft()[1])
        return out

    def start(self):
        import threading
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return self

    def _loop(self):
        while True:
            keepalive = False
            with self.cv:
                batch = self.due(self.now())
                if batch:
                    self.started = True
                elif self.started or not self.q:
                    self.cv.wait(None if not self.q else max(0.0, self.q[0][0] - self.now()))
                    continue
                else:
                    batch, keepalive = [NULL_PACKET] * 5, True        # nothing due yet: keep bytes flowing
            try:
                self.out.write(b"".join(batch))
                self.out.flush()
            except (BrokenPipeError, ValueError, OSError) as exc:
                self.err = exc
                return
            if keepalive:
                with self.cv:
                    self.cv.wait(min(0.2, max(0.0, self.q[0][0] - self.now())) if self.q else 0.2)


def log(msg):
    print("ts_dedupe: " + msg, file=sys.stderr, flush=True)


class Aligner:
    """Cuts a byte stream into 188-byte TS packets and realigns on the next run of sync bytes after lost sync."""

    def __init__(self):
        self.buf = b""

    def feed(self, chunk):
        self.buf += chunk
        cut = len(self.buf) - (len(self.buf) % PKT)
        data, self.buf = self.buf[:cut], self.buf[cut:]
        if data and data[0] != 0x47:  # lost sync: realign on the next run of sync bytes
            i = data.find(b"\x47")
            while i >= 0 and i + 2 * PKT < len(data) and not (data[i + PKT] == 0x47 and data[i + 2 * PKT] == 0x47):
                i = data.find(b"\x47", i + 1)
            data = data[i:] if i >= 0 else b""
            data = data[: len(data) - (len(data) % PKT)]
        return [data[i:i + PKT] for i in range(0, len(data), PKT)]


class Controller:
    """Active connection plus a standby, so a provider cut is a switch instead of a reconnect.

    Skipping the replay after a reconnect blinds the relay for tens of seconds (about 29 s normally, minutes after a read
    timeout, when the provider restarts far behind). The providers allow two connections, and a fresh connection is sent faster
    than real time at first, so a standby opened while the active one is still healthy catches up to the live edge. From the first
    keyframe within a few seconds of what the active connection has delivered it keeps its packets. When the active connection ends, those packets
    are fed through the same gate as any new connection (drop up to the last delivered frame, resume at a keyframe), so the output
    continues without a gap beyond at most one GOP. With no standby ready it falls back to a plain reconnect. A refused or dying
    standby backs off so the provider is not hammered. All methods run on one thread; sources are objects with .started, .got_data
    and .close().
    """

    CATCH_UP = 4 * 90000    # the standby starts buffering at a keyframe at most this far behind what the active connection delivered

    def __init__(self, relay, open_source, now=time.monotonic, sleep=time.sleep, standby_after=30.0, cap_bytes=48 << 20):
        self.relay, self.open_source, self.now, self.sleep = relay, open_source, now, sleep
        self.standby_after, self.cap = float(standby_after), cap_bytes
        self.active = self.standby = None
        self.sbuf, self.sopen, self.sbytes = [], False, 0
        self.failures = 0                 # consecutive active connections that gave nothing
        self.block_until, self.block_for = 0.0, 5.0

    def start(self):
        self.relay.new_connection()
        self.active = self.open_source()

    def close(self):
        for src in (self.active, self.standby):
            if src is not None:
                src.close()

    def on_data(self, src, pkts):
        src.got_data = True
        if src is self.active:
            for pkt in pkts:
                self.relay.feed(pkt)
        elif src is self.standby:
            self._standby_data(pkts)

    def _standby_data(self, pkts):
        for pkt in pkts:
            if self.sopen:
                self.sbuf.append(pkt)
                self.sbytes += PKT
            elif pkt[0] == 0x47 and pkt[1] & 0x40 and stream_kind(pkt) == "v" and is_keyframe(pkt):
                pts = parse_pts(pkt)
                if pts is not None and Relay.caught_up(pts, self.relay.last_v, self.CATCH_UP):
                    self.sopen, self.sbuf, self.sbytes = True, [pkt], PKT
                    log("standby caught up with the live edge")
        if self.sbytes > self.cap:
            log("standby buffer over %d MB, dropping it" % (self.cap >> 20))
            self._drop_standby(5.0)

    def _drop_standby(self, backoff):
        if self.standby is not None:
            self.standby.close()
        self.standby, self.sbuf, self.sopen, self.sbytes = None, [], False, 0
        self.block_until = self.now() + backoff

    def on_end(self, src, err):
        if src is self.standby:
            if src.got_data:
                self.block_for = 5.0
            else:
                self.block_for = min(self.block_for * 2, 600.0)       # refused or silent: back off, do not hammer the provider
            log("standby ended (%s); next attempt in %.0f s" % (err or "closed by provider", self.block_for))
            self._drop_standby(self.block_for)
            return
        if src is not self.active:
            return                                                    # a connection we already closed
        self.failures = 0 if src.got_data else self.failures + 1
        if err:
            log("%s (attempt %d)" % (err, max(self.failures, 1)))
        src.close()
        if self.standby is not None:
            buffered, opened = self.sbuf, self.sopen
            self.active, self.standby, self.sbuf, self.sopen, self.sbytes = self.standby, None, [], False, 0
            self.relay.new_connection()
            log("switched to the standby connection (%d packets buffered, caught up: %s)" % (len(buffered), opened))
            for pkt in buffered:
                self.relay.feed(pkt)
            return
        if self.failures:
            self.sleep(min(0.5 * self.failures, 3))
        self.relay.new_connection()
        self.active = self.open_source()

    def tick(self):
        if self.standby_after > 0 and self.active is not None and self.standby is None and self.now() >= self.block_until \
                and self.now() - self.active.started >= self.standby_after:
            self.standby = self.open_source()
            self.sbuf, self.sopen, self.sbytes = [], False, 0


class Source(threading.Thread):
    """One provider connection read on its own thread; packets and the end of the connection are put on the shared queue."""

    def __init__(self, url, headers, q, connect_timeout, read_timeout):
        super().__init__(daemon=True)
        self.url, self.headers, self.q, self.timeouts = url, headers, q, (connect_timeout, read_timeout)
        self.started, self.got_data = time.monotonic(), False
        self.stop, self.response = threading.Event(), None

    def close(self):
        self.stop.set()
        try:
            if self.response is not None:
                self.response.close()
        except Exception:
            pass

    def _put(self, item):
        while not self.stop.is_set():
            try:
                self.q.put(item, timeout=0.5)
                return
            except queue.Full:
                continue

    def run(self):
        import requests
        err = None
        try:
            with requests.get(self.url, headers=self.headers, stream=True, timeout=self.timeouts) as r:
                self.response = r
                if r.status_code != 200:
                    raise IOError("HTTP %d" % r.status_code)
                aligner = Aligner()
                for chunk in r.iter_content(65536):
                    if self.stop.is_set():
                        return
                    pkts = aligner.feed(chunk) if chunk else []
                    if pkts:
                        self._put((self, pkts, None))
        except Exception as exc:  # network error, provider reject, read timeout
            err = exc
        if not self.stop.is_set():
            self._put((self, None, err))


def run(url, user_agent, out=None, connect_timeout=5, read_timeout=6, delay=None, standby=None):
    out = out or sys.stdout.buffer
    delay = float(os.environ.get("TS_DEDUPE_DELAY", "0")) if delay is None else delay   # output time shift: off, see docs/guide/media.md
    standby = float(os.environ.get("TS_DEDUPE_STANDBY", "0")) if standby is None else standby   # seconds before the standby opens; 0 = off (unvalidated on live content)
    if delay > 0:
        out = Pacer(out, delay).start()
    relay = Relay(out)
    headers = {"User-Agent": user_agent or "VLC/3.0.20 LibVLC/3.0.20", "Connection": "keep-alive"}
    q = queue.Queue(400)

    def open_source():
        src = Source(url, headers, q, connect_timeout, read_timeout)
        src.start()
        return src

    ctl = Controller(relay, open_source, standby_after=standby)
    try:
        ctl.start()
        while True:
            try:
                src, pkts, err = q.get(timeout=1.0)
            except queue.Empty:
                ctl.tick()
                continue
            if pkts is None:
                ctl.on_end(src, err)
            else:
                ctl.on_data(src, pkts)
                out.flush()
            ctl.tick()
    except (BrokenPipeError, ValueError):
        return 0
    finally:
        ctl.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
