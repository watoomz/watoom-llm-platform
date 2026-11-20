#!/usr/bin/env python3
"""Post an OpenSpec change event to Discord. Dependency-free (stdlib only).

The webhook URL is read from a root-only file via --webhook-file and is never
printed, logged, or included in any committed artifact.

Two modes:
  --status   state-change: requires --change, --from-status, --to-status
  --blocked  needs-input: requires --change, --reason

Both modes require --project (repo/project name) so the Discord message is
self-identifying when multiple projects post to the same channel.
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request

p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
p.add_argument("--webhook-file", required=True, help="path to a root-only file containing the Discord webhook URL")
p.add_argument("--project", required=True, help="repo/project name shown in the Discord message")
p.add_argument("--change", required=True, help="OpenSpec change name")
mode = p.add_mutually_exclusive_group(required=True)
mode.add_argument("--status", action="store_true", help="report a status change (needs --from-status/--to-status)")
mode.add_argument("--blocked", action="store_true", help="report the change is blocked / needs user input (needs --reason)")
p.add_argument("--from-status")
p.add_argument("--to-status")
p.add_argument("--reason")
p.add_argument("--change-dir", help="optional OpenSpec change directory containing proposal.md and milestones.md")
a = p.parse_args()

DISCORD_FIELD_LIMIT = 1024


def clip(text, limit=DISCORD_FIELD_LIMIT):
    text = text.strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text or "(none)"


def read_optional(path):
    try:
        with open(path, "r", encoding="utf-8") as source:
            return source.read()
    except (OSError, UnicodeError):
        return ""


def section(markdown, heading):
    match = re.search(r"^##\s+" + re.escape(heading) + r"\s*$", markdown, re.I | re.M)
    if not match:
        return ""
    tail = markdown[match.end():]
    next_heading = re.search(r"^#{1,2}\s+", tail, re.M)
    return tail[:next_heading.start()] if next_heading else tail


def proposal_fields(change_dir):
    proposal = read_optional(os.path.join(change_dir, "proposal.md"))
    fields = []
    if not proposal:
        return fields

    summary = section(proposal, "Summary")
    if not summary:
        body = re.sub(r"^---\s*$.*?^---\s*$", "", proposal, flags=re.S | re.M).strip()
        paragraphs = re.split(r"\n\s*\n", body)
        summary = next((part for part in paragraphs if part.strip() and not part.lstrip().startswith("#")), "")
    if summary:
        fields.append({"name": "Change summary", "value": clip(summary, 900), "inline": False})

    criteria = section(proposal, "Acceptance Criteria")
    if criteria:
        items = re.findall(r"^\s*[-*+]\s+\[([ xX])\]\s+(.+?)\s*$", criteria, re.M)
        if items:
            done = sum(mark.lower() == "x" for mark, _ in items)
            rendered = "\n".join(f"{'✅' if mark.lower() == 'x' else '⬜'} {text}" for mark, text in items)
            fields.append({"name": f"Acceptance criteria ({done}/{len(items)} met)", "value": clip(rendered), "inline": False})
    return fields


def milestone_field(change_dir, status):
    content = read_optional(os.path.join(change_dir, "milestones.md"))
    if not content:
        return None
    # The repository convention stores milestones as YAML-like name/target_status
    # entries. Treat the current status as complete when it matches the target.
    milestones = re.findall(
        r"(?ms)^\s*-\s+name:\s*(.+?)\s*\n\s*target_status:\s*(.+?)\s*$", content
    )
    if not milestones:
        # Also support a simple Markdown checkbox list when present.
        entries = re.findall(r"^\s*[-*+]\s+\[([ xX])\]\s+(.+?)\s*$", content, re.M)
        if entries:
            done = sum(mark.lower() == "x" for mark, _ in entries)
            remaining = len(entries) - done
            current = next((name for mark, name in entries if mark.lower() != "x"), "All milestones complete")
            return {"name": "Milestone progress", "value": clip(f"{current} · {done}/{len(entries)} complete · {remaining} remaining"), "inline": False}
        return None
    completed = [name.strip().strip("'\"") for name, target in milestones if target.strip().strip("'\"").lower() == status.lower()]
    remaining = len(milestones) - len(completed)
    next_name = next((name.strip().strip("'\"") for name, _ in milestones if name.strip().strip("'\"") not in completed), "All milestones complete")
    return {"name": "Milestone progress", "value": clip(f"{next_name} · {len(completed)}/{len(milestones)} complete · {remaining} remaining"), "inline": False}


def work_so_far(change_dir):
    tasks = read_optional(os.path.join(change_dir, "tasks.md"))
    items = re.findall(r"^\s*[-*+]\s+\[([ xX])\]\s+(.+?)\s*$", tasks, re.M)
    if not items:
        return None
    done = [text for mark, text in items if mark.lower() == "x"]
    if not done:
        return None
    return {"name": f"Completed so far ({len(done)}/{len(items)} tasks)", "value": clip("\n".join(f"✅ {text}" for text in done)), "inline": False}

if a.status and (not a.from_status or not a.to_status):
    p.error("--status requires both --from-status and --to-status")
if a.blocked and not a.reason:
    p.error("--blocked requires --reason")

try:
    webhook_url = open(a.webhook_file, "r", encoding="utf-8").read().strip()
except OSError as exc:
    sys.exit(f"could not read --webhook-file {a.webhook_file!r}: {exc}")
if not webhook_url:
    sys.exit(f"--webhook-file {a.webhook_file!r} is empty")

now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
if a.status:
    title = f"[{a.project}] {a.change}: status updated"
    color = 0x5865F2
else:
    title = f"[{a.project}] {a.change}: blocked / needs input"
    color = 0xED4245

fields = []
if a.status:
    fields.append({"name": "Status", "value": clip(f"{a.from_status} → {a.to_status}"), "inline": True})
else:
    fields.append({"name": "⚠️ Reason · action needed", "value": clip(a.reason), "inline": False})

if a.change_dir:
    fields.extend(proposal_fields(a.change_dir))
    current_status = a.to_status if a.status else ""
    milestone = milestone_field(a.change_dir, current_status)
    if milestone:
        fields.append(milestone)
    if a.blocked:
        completed = work_so_far(a.change_dir)
        if completed:
            fields.append(completed)

embed = {
    "title": title,
    "color": color,
    "fields": fields[:25],
    "footer": {"text": now},
}
payload = json.dumps({"embeds": [embed]}, ensure_ascii=False).encode("utf-8")
request = urllib.request.Request(
    webhook_url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
)
try:
    with urllib.request.urlopen(request, timeout=15) as response:
        response.read()
except (urllib.error.URLError, OSError):
    # Exception text from urllib can include the request URL; keep it private.
    sys.exit("Discord webhook POST failed (details omitted to protect the webhook URL)")

print(f"notified: {title}")
