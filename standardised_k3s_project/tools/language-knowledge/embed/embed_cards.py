#!/usr/bin/env python3
"""Embed cards with the existing in-cluster BGE service into an Int8, L2-normalised matrix for the RAM engine.

Resumable (checkpoint every batch), rate limited, bounded: it shares the CPU embedding service with AgentMemory, so run it
off-peak or with --limit. Output: <out>/vectors.i8 (count*dim bytes, card order) + <out>/vectors.json (model, dim, count,
cards_sha = first 16 hex of sha256 of the cards text exactly as the engine computes it).
  embed_cards.py --cards cards.jsonl --out DIR [--url http://10.243.135.54:8000] [--batch 32] [--delay 0.2] [--limit N]
"""
import argparse, hashlib, json, math, os, sys, time, urllib.request

def card_text(card):
    parts = [card["symbol"], card.get("signature", ""), card.get("summary", "")]
    return " | ".join(p for p in parts if p)[:700]

def embed(url, model, texts, timeout=60):
    body = json.dumps({"model": model, "input": texts}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/v1/embeddings", body, {"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)["data"]
    return [d["embedding"] for d in sorted(data, key=lambda d: d["index"])]

def quantise(vec):
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return bytes((max(-127, min(127, round(x / norm * 127))) & 0xFF) for x in vec)

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cards", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--url", default="http://bge-embeddings.llama-cpp.svc.cluster.local:8000")
    ap.add_argument("--model", default="bge-small-en-v1.5"); ap.add_argument("--dim", type=int, default=384)
    ap.add_argument("--batch", type=int, default=32); ap.add_argument("--delay", type=float, default=0.2)
    ap.add_argument("--limit", type=int, default=0, help="stop after N cards (partial output is NOT loadable)")
    a = ap.parse_args(argv)
    text = open(a.cards, encoding="utf-8").read()
    sha = hashlib.sha256(text.encode()).hexdigest()[:16]
    cards, seen = [], set()
    for line in text.split("\n"):
        if line.strip():
            c = json.loads(line)
            if c["id"] not in seen: seen.add(c["id"]); cards.append(c)
    os.makedirs(a.out, exist_ok=True)
    part, state = os.path.join(a.out, "vectors.i8.part"), os.path.join(a.out, "vectors.state.json")
    done = 0
    if os.path.exists(state):
        st = json.load(open(state))
        if st["cards_sha"] == sha and st["model"] == a.model and os.path.exists(part):
            done = st["done"]; os.truncate(part, done * a.dim)
    target = min(len(cards), a.limit) if a.limit else len(cards)
    with open(part, "ab" if done else "wb") as out:
        while done < target:
            batch = cards[done:min(done + a.batch, target)]
            vecs = embed(a.url, a.model, [card_text(c) for c in batch])
            if any(len(v) != a.dim for v in vecs): raise SystemExit("unexpected embedding dimension")
            for v in vecs: out.write(quantise(v))
            out.flush(); os.fsync(out.fileno()); done += len(batch)
            json.dump({"cards_sha": sha, "model": a.model, "done": done}, open(state, "w"))
            time.sleep(a.delay)
    if done == len(cards):
        os.replace(part, os.path.join(a.out, "vectors.i8"))
        json.dump({"model": a.model, "dim": a.dim, "count": done, "cards_sha": sha}, open(os.path.join(a.out, "vectors.json"), "w"))
        os.remove(state)
        print(f"COMPLETE {done} vectors")
    else:
        print(f"PARTIAL {done}/{len(cards)} (resume by re-running)")

if __name__ == "__main__":
    main()
