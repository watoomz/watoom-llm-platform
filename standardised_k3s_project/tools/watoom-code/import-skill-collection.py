#!/usr/bin/env python3
"""Merge retained discovery metadata into the existing native catalog. Never approves or executes."""

import argparse, sqlite3, pathlib, hashlib, json


def merge(source, target):
    source = pathlib.Path(source).resolve(strict=True)
    target = pathlib.Path(target).resolve(strict=True)
    if source == target:
        raise ValueError("Discovery source and native catalog must differ")
    src = sqlite3.connect("file:" + str(source) + "?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    dst = sqlite3.connect(target)
    dst.execute("PRAGMA busy_timeout=10000")
    try:
        rows = src.execute(
            "SELECT id,repo,path,name,description,sha256,license,risk,validation FROM skills ORDER BY id LIMIT 1001"
        ).fetchall()
        if len(rows) > 1000:
            raise ValueError("Collection exceeds reviewed import budget")
        with dst:
            # Existing registry tables remain authoritative; only additive metadata columns/tables.
            columns = {row[1] for row in dst.execute("PRAGMA table_info(skills)")}
            if "raw" not in columns:
                dst.execute("ALTER TABLE skills ADD COLUMN raw TEXT NOT NULL DEFAULT ''")
            dst.execute(
                "CREATE TABLE IF NOT EXISTS skill_attributes(skill_id TEXT PRIMARY KEY,classification TEXT,categories TEXT,frameworks TEXT,dependencies TEXT)"
            )
            dst.execute("CREATE TABLE IF NOT EXISTS external_links(url TEXT PRIMARY KEY,discovered_in TEXT,state TEXT)")
            counts = {"inserted": 0, "preserved": 0}
            for row in rows:
                if dst.execute("SELECT 1 FROM skills WHERE id=?", (row["id"],)).fetchone():
                    counts["preserved"] += 1
                    continue
                source_row = src.execute("SELECT commit_sha FROM sources WHERE repo=?", (row["repo"],)).fetchone()
                existing = dst.execute("SELECT commit_sha FROM sources WHERE repo=?", (row["repo"],)).fetchone()
                if existing and existing[0] != source_row[0]:
                    raise ValueError("Conflicting source revision: " + row["repo"])
                if not existing:
                    dst.execute("INSERT INTO sources(repo,commit_sha) VALUES(?,?)", (row["repo"], source_row[0]))
                raw = src.execute("SELECT raw FROM skills WHERE id=?", (row["id"],)).fetchone()[0]
                if len(raw.encode()) > 65536:
                    raw = ""
                dst.execute(
                    "INSERT INTO skills(id,repo,path,name,description,sha256,license,risk,validation,raw) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (*tuple(row), raw),
                )
                dst.execute(
                    "INSERT INTO skills_fts(id,name,description) VALUES(?,?,?)",
                    (row["id"], row["name"], row["description"]),
                )
                attr = src.execute("SELECT * FROM skill_attributes WHERE skill_id=?", (row["id"],)).fetchone()
                if attr:
                    dst.execute("INSERT OR IGNORE INTO skill_attributes VALUES(?,?,?,?,?)", tuple(attr))
                counts["inserted"] += 1
            for row in src.execute("SELECT url,discovered_in,state FROM external_links LIMIT 1001"):
                dst.execute("INSERT OR IGNORE INTO external_links VALUES(?,?,?)", tuple(row))
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Catalog integrity failed")
        return {
            **counts,
            "discovered": dst.execute("SELECT count(*) FROM skills").fetchone()[0],
            "approved": dst.execute("SELECT count(*) FROM approvals").fetchone()[0],
            "external_references": dst.execute("SELECT count(*) FROM external_links").fetchone()[0],
        }
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True)
    a = p.parse_args()
    print(json.dumps(merge(a.source, a.target)))
