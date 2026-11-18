---
name: watoom-tickets
description: Log a ticket (to-do item) and post it to the owner's Discord. Use whenever the owner asks for or decides something, asks to log, post, notify or track something in Discord, or you find unfinished work or a bug outside your task. A ticket is posted to Discord by writing one small JSON request file, no command or webhook needed.
---

# WatooM tickets

Tickets are the owner's and the models' shared to-do list. Every new ticket and every status change is posted to the owner's Discord, into the channel for its state: New (created), In progress (doing, blocked), Closed (done) and Cancelled (dropped by the owner). You never touch Discord or a webhook yourself: writing the request file IS how you log a ticket to Discord. Nothing else is needed: you cannot run commands, so you write a request file and a timer creates the ticket within about two minutes.

## When to log a ticket
- **Every time the owner asks for something, and every time the owner and you decide something, log a ticket for it right away** (one per request or decision; the owner's words and the decision go in the body). If an open ticket already covers it, add a note to that ticket instead of a new one.
- You found a problem or improvement that is outside the task you were given.
- Work is left unfinished, blocked, or needs the owner's decision or a secret you cannot read.
- The owner says "remember", "don't forget", "add to the list", or "make a ticket".
- Do not log the same item twice (check `.opencode/tickets/*.status.json` first).

## How (quick start)
Write `<project>/.opencode/tickets/<id>.json` with the native write tool, for example `/data/ai/projects/homelab/homelab-llm/.opencode/tickets/crocodile-lake.json`:
`{"schema":1,"id":"crocodile-lake","model":"<your model name>","title":"...","body":"...","priority":"normal","project":"game"}`
Within about two minutes `crocodile-lake.status.json` appears next to it and the ticket is in Discord. Details:

You cannot run commands, so every action is a small JSON file written to `<project>/.opencode/tickets/<id>.json`. `<id>` is lower-case letters, digits and dashes (for example `creek-2-buried`) and is identical to the file name and the `id` field. A timer applies each file once within about two minutes, oldest first, and writes `<id>.status.json` next to it.

First read `<project>/.opencode/tickets/OPEN-TICKETS.md`: it is the generated list of everything open (id, status, priority, title). Check it before logging anything so you do not create a duplicate, and use it to find the ticket id for an update.

**Create** a ticket:
```json
{"schema": 1, "id": "creek-2-buried", "title": "Creek 2 water still buried after re-carve", "body": "What, where, how to reproduce, what was tried. Full paths.", "priority": "normal", "project": "game"}
```
`title` is one line a human reads in Discord. `body` holds the detail (up to 4000 characters). `priority` is `low`, `normal` or `high`. `project` is optional (the project folder name is used when it is missing).

**Start, block or finish** a ticket (`status` is `open`, `doing`, `blocked` or `done`; add a `note` saying what happened and a `pr` with the commit or PR link when you have one):
```json
{"schema": 1, "id": "creek-2-start", "action": "status", "ticket": "T-0007", "status": "doing", "note": "Re-carving with --depth-cm 300"}
```
**Add a note** (progress, a finding, a question for the owner):
```json
{"schema": 1, "id": "creek-2-note", "action": "note", "ticket": "T-0007", "text": "Buried at spline points 17-23; ZAS_Creek_1 spline is stale."}
```

- `<id>.status.json` says `{"state": "created", "ticket": "T-0008"}` or `{"state": "updated", ...}` when it worked, or `{"state": "duplicate", "ticket": "T-0008"}` when an active ticket already tracks the same request (your text was added to it as a note: do not file it again, work on or note that ticket instead), or `{"state": "rejected", "reason": "..."}` saying what to fix. Use a new `id` to retry; never edit an applied request.
- You cannot drop (cancel) a ticket; only the owner can. Mark it `done` only when the work is finished and checked, and say how in the note. Use `blocked` plus a note when you need the owner.
- Put the ticket id (T-0007) in your hand-off note, commit message or checkpoint so the work can be matched to it.
- Every create and update is posted to the owner's Discord channel. Never put secrets, tokens or webhook URLs in a ticket.

## Ownership: one model owns each ticket
- Put `"model": "<your model name>"` in every request file (create, status, note, change_request). The ticket you create is owned by you. An unowned ticket (made by the owner) is claimed by the first model that sets it to `doing`.
- Only the owning model may set status or add notes. If you are asked to work a ticket another model owns, do not edit it: write a change request, and the owner approves it by assigning the ticket to you. Then continue.
```json
{"schema": 1, "id": "dungeon-cr", "action": "change_request", "model": "my-model-name", "ticket": "T-0015", "text": "Owner asked me to take this over because ... ; I will do X."}
```
- A request rejected with "owned by ..." means: file the change request above and carry on with other work until it is approved.

## Owner commands (for reference)
`watoom-ticket assign T-0007 <model>` (give a ticket to a model; approves its change request), 
`watoom-ticket list`, `show T-0007`, `status T-0007 doing|blocked|done|dropped --note "..." --pr <url or commit>`, `note T-0007 "..."`, `digest`.

Discord keeps ONE message per ticket: later notes and status changes edit that message, and a status change that moves the ticket to another channel deletes the old message and posts it there. Before creating a ticket run `ticket list` (or read `OPEN-TICKETS.md` in the queue folder) and note on an existing one rather than filing a near-copy.
