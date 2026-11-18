#!/usr/bin/env python3
"""Copy this skill's SKILL.md and references/*.md byte-for-byte into the language-knowledge manual sources, then run the card gate.
  python3 sync_manual.py [--check]     --check: only compare (exit 1 on drift)
Cards live in tools/language-knowledge/manuals/watoom-godot-game/entries.jsonl (hand-written, source_span checked by manual_extract.py)."""
import filecmp, glob, json, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(SKILL, "..", "..", "..", "..", "..", ".."))
LK = os.path.join(ROOT, "tools", "language-knowledge")
SRC = os.path.join(LK, "manuals", "watoom-godot-game", "sources")


def pairs():
    docs = [os.path.join(SKILL, "SKILL.md")] + sorted(glob.glob(os.path.join(SKILL, "references", "*.md")))
    return [(d, os.path.join(SRC, os.path.basename(d))) for d in docs]


def drift():
    return [d for d, s in pairs() if not os.path.exists(s) or not filecmp.cmp(d, s, shallow=False)]


def main(argv):
    if not os.path.isdir(os.path.dirname(SRC)):
        print("language-knowledge manual dir not found (deployed copy?): nothing to sync")
        return 0
    if "--check" in argv:
        bad = drift()
        for b in bad:
            print("DRIFT: %s differs from its manuals/.../sources copy" % b)
        return 1 if bad else 0
    os.makedirs(SRC, exist_ok=True)
    for d, s in pairs():
        shutil.copyfile(d, s)
    sj = os.path.join(os.path.dirname(SRC), "source.json")
    meta = json.load(open(sj))
    meta["pages"] = [{"file": os.path.basename(d), "uri": "internal:ansible/roles/watoom-code/files/skills/watoom-godot-game/" + os.path.relpath(d, SKILL)} for d, _ in pairs()]
    json.dump(meta, open(sj, "w"), indent=2)
    open(sj, "a").write("\n")
    extra = [f for f in os.listdir(SRC) if f not in {os.path.basename(d) for d, _ in pairs()}]
    for f in extra:
        print("note: stale source not in skill: %s" % f)
    r = subprocess.run([sys.executable, os.path.join(LK, "extract", "manual_extract.py"), "--manuals-root", os.path.join(LK, "manuals"),
                        "--product", "watoom-godot-game", "--out", os.path.join(os.environ.get("TMPDIR", "/tmp"), "wlk_gg_out")])
    return r.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
