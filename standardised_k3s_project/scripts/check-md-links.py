#!/usr/bin/env python3
"""Fail on broken relative links in tracked Markdown (T-0115).

Skipped: vendored manuals/skills content, and overlay templates under tools/git/*overlay*/ whose links resolve
in the repository they are copied into, not here.
"""
import os
import re
import subprocess
import sys

SKIP = ("tools/language-knowledge/manuals/", "ansible/roles/watoom-code/files/skills/")
LINK = re.compile(r"\]\(([^)#\s]+)")


def main() -> int:
    files = subprocess.check_output(["git", "ls-files", "*.md"], text=True).split()
    broken = []
    for f in files:
        if f.startswith(SKIP) or re.match(r"tools/git/[^/]*overlay", f):
            continue
        text = open(f, encoding="utf-8", errors="ignore").read()
        text = re.sub(r"```.*?```", "", text, flags=re.S)  # links inside code blocks are examples
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "/", "<")) or "{{" in target:
                continue
            if not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(f), target))):
                broken.append(f"{f} -> {target}")
    for line in broken:
        print("BROKEN:", line)
    print(f"{'FAIL' if broken else 'OK'}: {len(files)} Markdown files, {len(broken)} broken relative links")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
