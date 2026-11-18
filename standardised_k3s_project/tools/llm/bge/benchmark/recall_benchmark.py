#!/usr/bin/env python3
"""Recall@3/@5 of AgentMemory search for paraphrased queries, BM25-only vs hybrid.

Seeds each target AgentMemory (disposable instances only) with the fixture records
plus optional distractor texts, then runs every paraphrased query through the same
/agentmemory/search call the WatooM-Code client uses.
"""
import argparse, json, pathlib, statistics, time, urllib.request

def call(base, secret, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"authorization": "Bearer " + secret, "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)

def run(base, secret, records, distractors, project="bench", agent="watoom-builder"):
    marker = {}
    for text in distractors:
        call(base, secret, "/agentmemory/remember", {"content": text, "project": project, "agentId": agent})
    for r in records:
        saved = call(base, secret, "/agentmemory/remember", {"content": r["text"], "project": project, "agentId": agent})
        marker[saved["memory"]["id"]] = r["id"]
    time.sleep(2)
    hits3 = hits5 = 0; latency = []
    for r in records:
        t = time.monotonic()
        res = call(base, secret, "/agentmemory/search", {"query": r["query"], "project": project, "agentId": agent, "limit": 5, "format": "full", "token_budget": 4096})
        latency.append((time.monotonic() - t) * 1000)
        ids = []
        for item in res.get("results", []):
            obs = item.get("observation", {})
            ids.append(marker.get(obs.get("id")) or next((v for k, v in marker.items() if k in json.dumps(item)), None))
        hits3 += r["id"] in ids[:3]; hits5 += r["id"] in ids[:5]
    n = len(records)
    return {"recall_at_3": round(hits3 / n, 3), "recall_at_5": round(hits5 / n, 3), "queries": n,
            "search_ms_p50": round(statistics.median(latency), 1), "search_ms_max": round(max(latency), 1)}

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", action="append", required=True, help="name=http://host:port")
    p.add_argument("--secret", required=True)
    p.add_argument("--fixture", type=pathlib.Path, default=pathlib.Path(__file__).with_name("recall-fixture.json"))
    p.add_argument("--distractors", type=pathlib.Path, help="JSON list of distractor texts")
    a = p.parse_args()
    records = json.loads(a.fixture.read_text())["records"]
    distractors = json.loads(a.distractors.read_text()) if a.distractors else []
    out = {name: run(url, a.secret, records, distractors) for name, url in (t.split("=", 1) for t in a.target)}
    out["distractors"] = len(distractors)
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
