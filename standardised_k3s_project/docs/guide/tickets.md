---
title: Tickets (to-do list with Discord alerts)
nav: Tickets
summary: The shared to-do list for you and the models. How to log, start, block and finish an item, how the models use it without running commands, what appears in Discord, and what to check when something does not show up.
---

## What it is

A small shared to-do list so nothing is forgotten, whether you or a model noticed it. Every ticket has an id (`T-0001`), a title, a status, a priority, an optional project and PR or commit link, and a history of notes. Every new ticket, status change and note is posted to your Discord channel, and a digest of everything still open is posted at 08:30 each day.

| Status | Meaning |
|---|---|
| `open` | Logged, nobody has started it |
| `doing` | Someone is working on it now |
| `blocked` | Waiting for you or for something outside the work (the latest note says what) |
| `done` | Finished and checked (the note says how; a PR or commit link is attached when there is one) |
| `dropped` | Cancelled. Only you can set this; models cannot |

Priorities are `high`, `normal` and `low`; lists show high first.

## Using it yourself

Run these on the server. `watoom-ticket` is installed at `/usr/local/bin/watoom-ticket` (source `tools/tickets/ticket.py`).

| Task | Command |
|---|---|
| Log something | `watoom-ticket add "Fix the creek gap" --priority high --project game --body "Details and full paths"` |
| See what is open | `watoom-ticket list` (add `--all` for finished ones, `--project game` to filter) |
| Read one ticket with its notes | `watoom-ticket show T-0004` |
| Start, block or finish | `watoom-ticket status T-0004 doing`, `... blocked --note "needs the webhook"`, `... done --note "verified in the viewport" --pr <commit or URL>` |
| Add a note | `watoom-ticket note T-0004 "tried a deeper carve, still buried at 17-23"` |
| Post the open list now | `watoom-ticket digest` |

The tickets live in `/data/ai/tickets/tickets.json`. It is one file with atomic, locked writes, so the commands and the models can use it at the same time.

## How the models use it

Models cannot run commands, so they write small request files and a timer turns them into ticket changes within about two minutes. This is the same pattern as the change-request and ESP32 queues.

1. The model reads `<project>/.opencode/tickets/OPEN-TICKETS.md`, a generated list of every open ticket. It uses it to avoid duplicates and to find ticket ids.
2. It writes `<project>/.opencode/tickets/<id>.json`, where the id is lower-case letters, digits and dashes and is the same as the file name.
3. `watoom-tickets-ingest.timer` runs every 2 minutes, applies each new request once (oldest first, so a later "done" wins), and writes `<id>.status.json` next to it with `created`, `updated` or `rejected` and the reason.

| Request | File content |
|---|---|
| Create | `{"schema":1,"id":"creek-gap","title":"Creek 2 still buried","body":"details","priority":"high","project":"game"}` |
| Start, block, finish | `{"schema":1,"id":"creek-gap-start","action":"status","ticket":"T-0007","status":"doing","note":"re-carving"}` (statuses `open`, `doing`, `blocked`, `done`; optional `pr`) |
| Note | `{"schema":1,"id":"creek-gap-note","action":"note","ticket":"T-0007","text":"buried at points 17-23"}` |

The `watoom-tickets` skill and a short block in every assembled agent prompt (`_src/shared/73_tickets.md`) tell the models when to log a ticket: work they will not finish this turn, a problem outside their task, something left blocked, or you saying "remember" or "don't forget". The models are told to mark a ticket `done` only when it is finished and verified, and to say how in the note.

> [!NOTE]
> A model-created ticket shows `model:<project folder>` as its author in the ticket and in Discord. Your own commands show your user name.

## In Discord

Each change is one message with the ticket id, title, status colour (blue open, amber doing, red blocked, green done, grey dropped), priority, project, the PR or commit link and the latest note. The daily digest lists every open ticket, highest priority first. Discord is only a notification: the source of truth is `/data/ai/tickets/tickets.json`, and a failed post never blocks a ticket change.

## Setup and files

| Item | Detail |
|---|---|
| Webhook | The channel's webhook URL in the root-only file `/data/ai/secrets/discord_tickets_webhook` (change the path with `WATOOM_TICKET_WEBHOOK_FILE`). The URL is never printed, logged or stored in the tickets. To rotate it, create a new webhook in Discord (Channel Settings, Integrations) and overwrite the file. |
| Timers | `watoom-tickets-ingest.timer` (every 2 minutes) and `watoom-tickets-digest.timer` (08:30 daily), units under `tools/tickets/`, installed to `/etc/systemd/system/` |
| Queue folders | `/data/ai/projects/*/*/.opencode/tickets` (only real directories, never symlinks; files over 16 KB are rejected) |
| Test | `python3 tools/tickets/test_ticket.py` (10 tests, including a fake Discord server) |

> [!RULE]
> Tickets are posted to Discord, so never put secrets, tokens or webhook URLs in a title, body or note.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| A model's request never became a ticket | Check for `<id>.status.json` next to it. No file after 2 minutes: `systemctl status watoom-tickets-ingest.timer`, and check the request is in a project folder matching `/data/ai/projects/*/*/.opencode/tickets`. |
| Status says `rejected` | The `reason` says what is wrong: file name and `id` differ, `schema` is not 1, the ticket id does not exist, or a model tried to set `dropped`. The model sends a new request with a new id. |
| Tickets are created but nothing appears in Discord | The command prints `(not posted to Discord)` when the webhook file is missing or empty, and a one-line `discord: not sent (...)` error when Discord refuses it. Check the file exists and is the full URL; a deleted or rotated webhook needs the file replaced. |
| `OPEN-TICKETS.md` is old | It is rewritten on every ingest run, so a stale time in its heading means the timer is not running. |
| Two tickets for the same item | Close the second with `watoom-ticket status T-00NN dropped --note "duplicate of T-00MM"`. |
