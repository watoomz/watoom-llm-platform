#!/usr/bin/env python3
"""OpenAI-compatible /v1/embeddings front end for a llama.cpp BGE server.

BGE accepts at most 512 tokens and llama-server rejects longer embedding inputs,
while AgentMemory sends up to 16,000 characters and fails a whole batch on one
error. Each input is tokenized; inputs over the window are split into overlapping
windows (each wrapped in [CLS] ... [SEP]) and the window vectors are combined into
one length-weighted, L2-normalised mean, so the whole record stays retrievable.
Bounded concurrency, a content-hash LRU cache and Prometheus metrics. Batch requests (bulk
re-embedding) are paced to a window rate so they cannot saturate the GPU shared with the
coding model; interactive queries are never paced. Stdlib only.
"""
import argparse, collections, hashlib, http.server, json, math, threading, time, urllib.request

WINDOW, OVERLAP = 510, 64  # tokens per window excluding [CLS]/[SEP]
INTERACTIVE_WINDOWS = 8  # requests at or below this are queries, never paced
# 2026-11-20: AgentMemory aborts an embedding call after ~15 s and retries. A batch that would sleep longer than this
# is refused at once (503, nothing reserved) instead of sleeping past the client's timeout and still consuming backend
# time for an answer nobody reads -- that backlog starved recall queries ("AgentMemory retrieval unavailable").
MAX_BATCH_WAIT = 8.0

class Busy(Exception):
    pass
# Request bounds (the service listens on all interfaces for the pods, with no authentication, so size is the only brake on
# memory, tokenizer and GPU work). AgentMemory sends up to 16,000 characters per input and up to 256 inputs per call.
MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_INPUTS = 256
MAX_TEXT_CHARS = 32_000
MAX_TOTAL_CHARS = 4_200_000

def check_body_size(content_length):
    """(status, message) when the declared body is too large, else None."""
    if content_length < 0:  # read(-1) would mean "until EOF" and bypass the limit
        return 400, "invalid content-length"
    if content_length > MAX_BODY_BYTES:
        return 413, "request body over %d bytes" % MAX_BODY_BYTES
    return None

def check_inputs(texts):
    """(status, message) when the parsed inputs must be refused, else None. A missing input (None) is refused too."""
    if not isinstance(texts, list) or not texts or len(texts) > MAX_INPUTS or not all(isinstance(t, str) and t for t in texts):
        return 400, "input must be a non-empty string or up to %d non-empty strings" % MAX_INPUTS
    if any(len(t) > MAX_TEXT_CHARS for t in texts):
        return 413, "an input is over %d characters" % MAX_TEXT_CHARS
    if sum(len(t) for t in texts) > MAX_TOTAL_CHARS:
        return 413, "inputs total over %d characters" % MAX_TOTAL_CHARS
    return None

def windows(tokens, size=WINDOW, overlap=OVERLAP):
    if len(tokens) <= size:
        return [tokens]
    step, out = size - overlap, []
    for start in range(0, len(tokens), step):
        out.append(tokens[start:start + size])
        if start + size >= len(tokens):
            break
    return out

def combine(vectors, weights):
    dims = len(vectors[0])
    mean = [sum(v[i] * w for v, w in zip(vectors, weights)) for i in range(dims)]
    norm = math.sqrt(sum(x * x for x in mean)) or 1.0
    return [x / norm for x in mean]

class Embedder:
    def __init__(self, backend, cls_id, sep_id, cache_size=20000, concurrency=4, post=None, batch_rate=100.0,
                 busy_file=None, busy_rate=25.0, max_wait=MAX_BATCH_WAIT):
        self.backend, self.cls, self.sep = backend.rstrip("/"), cls_id, sep_id
        self.cache, self.cache_size, self.lock = collections.OrderedDict(), cache_size, threading.Lock()
        self.slots = threading.BoundedSemaphore(concurrency)
        # Batches may hold at most concurrency-1 backend slots, so a recall query always finds one free.
        self.batch_slots = threading.BoundedSemaphore(max(1, concurrency - 1))
        self.max_wait = max_wait
        self.post = post or self._post
        self.metrics = collections.Counter()
        self.batch_rate, self.next_free, self.pacer = batch_rate, 0.0, threading.Lock()
        self.busy_file, self.busy_rate, self.busy_seen = busy_file, busy_rate, (-1.0, False)

    def busy(self):
        """True while the GPU controller reports active chat inference; stale or unreadable means not busy."""
        if not self.busy_file:
            return False
        checked, value = self.busy_seen
        now = time.monotonic()
        if now - checked < 1.0:
            return value
        try:
            with open(self.busy_file) as f:
                status = json.load(f)
            value = status.get("activeRequests", 0) > 0 and time.time() * 1000 - status["sampledAt"] < 10000
        except (OSError, ValueError, KeyError, TypeError):
            value = False
        self.busy_seen = (now, value)
        return value

    def pace(self, count):
        """Reserve backend time for a batch at batch_rate windows/s (busy_rate while the primary
        model is serving a request); returns the wait applied."""
        if count <= INTERACTIVE_WINDOWS or self.batch_rate <= 0:
            return 0.0
        rate = self.batch_rate
        if self.busy_rate > 0 and self.busy():
            rate = min(rate, self.busy_rate)
            self.metrics["busy_paced_batches_total"] += 1
        with self.pacer:
            now = time.monotonic()
            start = max(now, self.next_free)
            if self.max_wait and start - now > self.max_wait:
                self.metrics["busy_refused_batches_total"] += 1
                raise Busy("batch pacing queue full; retry later")
            self.next_free = start + count / rate
        wait = start - now
        if wait > 0:
            time.sleep(wait)
        self.metrics["paced_seconds_total"] += wait
        return wait

    def _post(self, path, body, timeout=60):
        req = urllib.request.Request(self.backend + path, data=json.dumps(body).encode(), headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)

    def _cached(self, key):
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key); self.metrics["cache_hits"] += 1
                return self.cache[key]
        return None

    def _store(self, key, vector):
        with self.lock:
            self.cache[key] = vector; self.cache.move_to_end(key)
            while len(self.cache) > self.cache_size:
                self.cache.popitem(last=False)

    def embed(self, texts):
        keys = [hashlib.sha256(t.encode()).hexdigest() for t in texts]
        out = [self._cached(k) for k in keys]
        todo = [i for i, v in enumerate(out) if v is None]
        if todo:
            pieces, owner = [], []
            with self.slots:  # tokenizing is backend work too; bounded, but released before any pacing sleep
                for i in todo:
                    tokens = self.post("/tokenize", {"content": texts[i], "add_special": False})["tokens"]
                    parts = windows(tokens)
                    self.metrics["chunked_inputs"] += len(parts) > 1
                    for part in parts:
                        pieces.append([self.cls, *part, self.sep]); owner.append(i)
            batch = len(pieces) > INTERACTIVE_WINDOWS
            # Pace BEFORE taking a backend slot, so a sleeping batch never blocks a query.
            if batch:
                self.pace(len(pieces))
            gate = self.batch_slots if batch else threading.BoundedSemaphore(1)
            with gate, self.slots:
                started = time.monotonic()
                data = self.post("/v1/embeddings", {"input": pieces})["data"]
                vectors = [d["embedding"] for d in sorted(data, key=lambda d: d["index"])]
                for i in todo:
                    mine = [(vectors[j], len(pieces[j])) for j, o in enumerate(owner) if o == i]
                    out[i] = mine[0][0] if len(mine) == 1 else combine([v for v, _ in mine], [w for _, w in mine])
                    self._store(keys[i], out[i])
                self.metrics["embedded_inputs"] += len(todo); self.metrics["backend_windows"] += len(pieces)
                self.metrics["backend_seconds_total"] += time.monotonic() - started
        self.metrics["requests"] += 1
        return out

def serve(embedder, host, port, model):
    class Handler(http.server.BaseHTTPRequestHandler):
        def reply(self, code, body, kind="application/json"):
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code); self.send_header("content-type", kind); self.send_header("content-length", str(len(raw)))
            self.end_headers(); self.wfile.write(raw)
        def do_GET(self):
            if self.path == "/health":
                try:
                    urllib.request.urlopen(embedder.backend + "/health", timeout=3).read()
                    return self.reply(200, {"status": "ok"})
                except Exception as error:
                    return self.reply(503, {"status": "unavailable", "error": str(error)[:200]})
            if self.path == "/metrics":
                lines = [f"watoom_bge_{k} {v}" for k, v in sorted(embedder.metrics.items())] + [f"watoom_bge_cache_entries {len(embedder.cache)}"]
                return self.reply(200, ("\n".join(lines) + "\n").encode(), "text/plain; version=0.0.4")
            self.reply(404, {"error": "not found"})
        def do_POST(self):
            if self.path not in ("/v1/embeddings", "/embeddings"):
                return self.reply(404, {"error": "not found"})
            try:
                length = int(self.headers.get("content-length", 0) or 0)
                refused = check_body_size(length)
                if refused:
                    return self.reply(refused[0], {"error": {"message": refused[1]}})
                body = json.loads(self.rfile.read(length))
                inputs = body.get("input")
                texts = [inputs] if isinstance(inputs, str) else inputs
                refused = check_inputs(texts)
                if refused:
                    return self.reply(refused[0], {"error": {"message": refused[1]}})
                try:
                    vectors = embedder.embed(texts)
                except Busy as busy:
                    self.send_response(503); self.send_header("retry-after", "10"); self.send_header("content-type", "application/json")
                    raw = json.dumps({"error": {"message": str(busy)}}).encode()
                    self.send_header("content-length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
                    return
                self.reply(200, {"object": "list", "model": model,
                                 "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)]})
            except Exception as error:
                embedder.metrics["errors"] += 1
                self.reply(502, {"error": {"message": "embedding backend failure: " + str(error)[:300]}})
        def log_message(self, *args):
            pass
    http.server.ThreadingHTTPServer((host, port), Handler).serve_forever()

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--backend", default="http://127.0.0.1:8081")
    p.add_argument("--host", default="0.0.0.0"); p.add_argument("--port", type=int, default=8000)
    p.add_argument("--model", default="bge-small-en-v1.5")
    p.add_argument("--cls-id", type=int, default=101); p.add_argument("--sep-id", type=int, default=102)
    p.add_argument("--concurrency", type=int, default=4); p.add_argument("--cache-size", type=int, default=20000)
    p.add_argument("--batch-rate", type=float, default=100.0, help="max windows/s for batch requests; 0 disables pacing")
    p.add_argument("--busy-file", help="GPU controller status JSON; activeRequests>0 lowers batches to --busy-rate")
    p.add_argument("--busy-rate", type=float, default=25.0, help="max batch windows/s while the primary model is busy")
    p.add_argument("--max-batch-wait", type=float, default=MAX_BATCH_WAIT, help="refuse (503) a batch that would wait longer than this; 0 = never refuse")
    a = p.parse_args()
    serve(Embedder(a.backend, a.cls_id, a.sep_id, a.cache_size, a.concurrency, batch_rate=a.batch_rate, busy_file=a.busy_file, busy_rate=a.busy_rate, max_wait=a.max_batch_wait), a.host, a.port, a.model)

if __name__ == "__main__":
    main()
