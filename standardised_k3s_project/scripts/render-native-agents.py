#!/usr/bin/env python3
"""Assemble the watoom-code native agent definitions from single-source fragments.

Source of truth:
    ansible/roles/opencode-agent/files/v2-native/_src/
        assembly.json            -- ordered fragment list per role
        shared/*.md              -- fragments shared by >1 role
        roles/<role>/*.md        -- role-specific fragments

Output (generated; do not hand-edit):
    ansible/roles/opencode-agent/files/v2-native/agents/<role>.md

Each <role>.md is the byte-exact concatenation (no separator) of the fragment
files listed for that role in assembly.json. Only the roles present in
assembly.json are generated; other agents (watoom-creative-writer, watoom-kali)
are left untouched.

Usage:
    render-native-agents.py           regenerate the role .md files
    render-native-agents.py --check   verify on-disk .md match the source (CI);
                                      exit 1 and print a diff on any drift
"""
from pathlib import Path
import difflib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ansible/roles/opencode-agent/files/v2-native/_src"
OUT = ROOT / "ansible/roles/opencode-agent/files/v2-native/agents"
ASSEMBLY = SRC / "assembly.json"


def render(role: str, fragments: list[str]) -> str:
    parts = []
    for frag in fragments:
        path = SRC / frag
        if not path.is_file():
            sys.exit(f"ERROR [{role}]: missing fragment {frag}")
        parts.append(path.read_text())
    return "".join(parts)


def main() -> int:
    check = "--check" in sys.argv[1:]
    assembly = json.loads(ASSEMBLY.read_text())
    drift = False
    for role, fragments in assembly.items():
        content = render(role, fragments)
        dest = OUT / f"{role}.md"
        if check:
            current = dest.read_text() if dest.is_file() else ""
            if current != content:
                drift = True
                print(f"DRIFT: {dest.relative_to(ROOT)}")
                sys.stdout.writelines(
                    difflib.unified_diff(
                        current.splitlines(keepends=True),
                        content.splitlines(keepends=True),
                        fromfile=f"{role}.md (on disk)",
                        tofile=f"{role}.md (from _src)",
                    )
                )
        else:
            dest.write_text(content)
            print(f"wrote {dest.relative_to(ROOT)} ({len(content)} bytes, {len(fragments)} fragments)")
    if check:
        if drift:
            print("\nFAIL: generated agent defs are out of date; run render-native-agents.py")
            return 1
        print("OK: all generated agent defs match _src")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
