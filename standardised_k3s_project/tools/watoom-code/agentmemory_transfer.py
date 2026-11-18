#!/usr/bin/env python3
"""Paginated AgentMemory export/import that never exceeds the engine transport frame.

AgentMemory's own /agentmemory/export returns every memory in one response and fails past
~15 MiB. Export here reads the file-based KV store read-only (each collection file is replaced
atomically by the engine) into checksummed JSON-lines pages. Import replays pages through
/agentmemory/import with strategy "skip" (existing ids untouched; never "replace"), recording a
checkpoint after each page so an interrupted import resumes without duplicates. Derived BM25 and
vector indexes are not exported; AgentMemory rebuilds them.

  export --store /data/ai/watoom-code/memory/state_store.db --out DIR
  import --export DIR --url http://agentmemory:3111 --secret-file FILE
  verify --export DIR --store STORE_DIR
"""
import argparse, hashlib, json, os, pathlib, sys, time, urllib.request, urllib.parse

# Store collection file -> import field. Operational logs (audit, health) are not memory content.
COLLECTIONS = {"mem:memories": "memories", "mem:lessons": "lessons"}
VERSION = "0.9.29"
PAGE_BYTES = 4 * 1024 * 1024


def read_collection(path):
    """A collection file is one JSON object of id -> record followed by a short binary trailer."""
    text = path.read_bytes().decode("utf-8", errors="surrogateescape")
    value, _ = json.JSONDecoder().raw_decode(text)
    if not isinstance(value, dict):
        raise ValueError("unexpected collection shape in " + path.name)
    return value


def atomic(path, data):
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def export(store, out, page_bytes):
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    manifest = {"version": VERSION, "exportedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": str(store), "collections": {}}
    for name, field in COLLECTIONS.items():
        path = store / (urllib.parse.quote(name, safe="") + ".bin")
        records = list(read_collection(path).values()) if path.is_file() else []
        records.sort(key=lambda r: (str(r.get("createdAt", "")), str(r.get("id", ""))))
        pages, page, size = [], [], 0
        def flush():
            nonlocal page, size
            if not page:
                return
            body = ("\n".join(page) + "\n").encode()
            file = "%s-%05d.jsonl" % (field, len(pages))
            atomic(out / file, body)
            pages.append({"file": file, "records": len(page), "sha256": hashlib.sha256(body).hexdigest()})
            page, size = [], 0
        for record in records:
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            if len(line.encode()) > page_bytes:
                raise ValueError("single %s record exceeds the page size" % field)
            if size + len(line.encode()) + 1 > page_bytes:
                flush()
            page.append(line)
            size += len(line.encode()) + 1
        flush()
        manifest["collections"][field] = {"records": len(records), "pages": pages}
    atomic(out / "manifest.json", json.dumps(manifest, indent=2).encode())
    return manifest


def load_page(directory, entry):
    body = (directory / entry["file"]).read_bytes()
    if hashlib.sha256(body).hexdigest() != entry["sha256"]:
        raise ValueError("page checksum mismatch: " + entry["file"])
    return [json.loads(line) for line in body.decode().splitlines() if line]


def post(url, secret, body, timeout=600):
    request = urllib.request.Request(
        url.rstrip("/") + "/agentmemory/import",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json", **({"authorization": "Bearer " + secret} if secret else {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def import_pages(directory, url, secret, sender=post):
    manifest = json.loads((directory / "manifest.json").read_text())
    state_path = directory / "import-checkpoint.json"
    done = set(json.loads(state_path.read_text())["done"]) if state_path.is_file() else set()
    totals = {"pages": 0, "imported": 0, "skipped": 0}
    for field, collection in manifest["collections"].items():
        for entry in collection["pages"]:
            if entry["file"] in done:
                continue
            records = load_page(directory, entry)
            export_data = {"version": manifest["version"], "exportedAt": manifest["exportedAt"], "sessions": [], "observations": {}, "summaries": [], "memories": [], field: records}
            result = sender(url, secret, {"exportData": export_data, "strategy": "skip"})
            if result.get("success") is False:
                raise RuntimeError("import rejected %s: %s" % (entry["file"], str(result.get("error"))[:300]))
            stats = result.get("stats", result)
            totals["pages"] += 1
            totals["imported"] += int(stats.get(field, 0) or 0)
            totals["skipped"] += int(stats.get("skipped", 0) or 0)
            done.add(entry["file"])
            atomic(state_path, json.dumps({"done": sorted(done)}).encode())
    return totals


def verify(directory, store):
    manifest = json.loads((directory / "manifest.json").read_text())
    report = {}
    for name, field in COLLECTIONS.items():
        exported = {r["id"] for entry in manifest["collections"].get(field, {"pages": []})["pages"] for r in load_page(directory, entry) if "id" in r}
        path = store / (urllib.parse.quote(name, safe="") + ".bin")
        present = set(read_collection(path)) if path.is_file() else set()
        report[field] = {"exported": len(exported), "present": len(present & exported), "missing": len(exported - present)}
    report["status"] = "PASS" if all(v["missing"] == 0 for k, v in report.items() if isinstance(v, dict)) else "FAIL"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    e = sub.add_parser("export"); e.add_argument("--store", type=pathlib.Path, required=True); e.add_argument("--out", type=pathlib.Path, required=True); e.add_argument("--page-bytes", type=int, default=PAGE_BYTES)
    i = sub.add_parser("import"); i.add_argument("--export", type=pathlib.Path, required=True); i.add_argument("--url", required=True); i.add_argument("--secret-file", type=pathlib.Path)
    v = sub.add_parser("verify"); v.add_argument("--export", type=pathlib.Path, required=True); v.add_argument("--store", type=pathlib.Path, required=True)
    a = parser.parse_args()
    if a.action == "export":
        manifest = export(a.store.resolve(strict=True), a.out, a.page_bytes)
        print(json.dumps({k: {"records": c["records"], "pages": len(c["pages"])} for k, c in manifest["collections"].items()}))
    elif a.action == "import":
        secret = a.secret_file.read_text().strip() if a.secret_file else os.environ.get("AGENTMEMORY_SECRET", "")
        print(json.dumps(import_pages(a.export, a.url, secret)))
    else:
        report = verify(a.export, a.store)
        print(json.dumps(report))
        sys.exit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
