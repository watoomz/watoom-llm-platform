# Tickets board

A kanban page for the homelab to-do tickets, at **https://glance.internal.homelab.example/tickets/**. The owner, the Claude Code sessions (Sonnet, Sabre) and the local models all work the same tickets. Verified live 2026-11-18. The full design, with the reasoning behind each choice, is `tools/tickets/kanban-design.md`.

## What it is

- The ticket store is unchanged: `/data/ai/tickets/tickets.json`, written by `tools/tickets/ticket.py` (installed as `/usr/local/bin/watoom-ticket`). The board is a second front end on that store; the CLI, the model queue and the Discord posts keep working.
- Two processes, like the skill editor: a **UI pod** `tickets-board` in namespace `glance` (port 8789, no store access) and a **root broker** `watoom-tickets-board-broker` (systemd) that imports `ticket.py` and does every write over a unix socket.
- Plain HTML, CSS and JavaScript, no build step. The board refreshes by polling every 10 seconds.

## Columns and lanes

Columns (the ticket field `queue`): Requests, Issues, Backlog, **In progress**, Completed, Cancelled, Obsolete. `status` stays the authority (open, doing, blocked, done, dropped) and `queue` refines it. In progress is split into one lane per agent; the lane is the ticket's `owner`. A model not in the registry that claims a ticket (`model:<name>`) gets a lane automatically.

The Glance Command Center page shows a read-only counts widget (queue counts, lane counts, blocked, change requests) from `/tickets/api/summary`: numbers only, no titles or text. The Hub page has a "Tickets board" link.

## Who can do what

| Who | Own ticket | Another agent's ticket | Ticket marked shared | Unowned ticket |
|---|---|---|---|---|
| Owner | everything | everything | everything | everything |
| Agent | note, status, move, edit | rejected; file a change request | note, status, move, edit; moving it into its own lane takes it | starting it claims it |

Only the owner assigns an owner, drops a ticket (Cancelled or Obsolete), changes `shared` after creation, or approves a change request. A **shared** ("global") ticket can be worked by any agent: set it at creation (the form checkbox, `ticket.py add --shared`, or `"shared": true` in a queue request).

## Signing in

- **Owner:** password and a session cookie. The cookie lasts about ten years at the owner's request (a pod restart still signs everyone out, because sessions are in memory). The password is generated once by the role and kept at `/data/ai/private/tickets-board/password` (root; do not paste it into tickets, they sync to Discord).
- **Agents:** one bearer token each, `Authorization: Bearer <token>`, from `/data/ai/private/tickets-board/tokens/<id>` (root, mode 0600). Only the hashes are given to the pod.
- Writes also check the Origin header and a CSRF token.
- The CLI and the model queue still use the declared `--by` name, as before.

## HTTP API (under `/tickets`)

`GET /api/session`, `GET /api/board`, `GET /api/tickets/<id>`, `POST /api/tickets` (create), `POST /api/tickets/<id>/move`, `/note`, `/edit`, `/change-request`, `POST /api/tickets/<id>/change-request/<n>` (owner decision: assign, share, reject), and the unauthenticated `GET /api/summary`. Errors: 400 bad input, 401 not signed in, 403 refused (Origin/CSRF or ownership), 404 no such ticket, 409 the ticket changed since `if_updated`.

## CLI additions

```
ticket.py add "title" [--queue requests|issues|backlog] [--shared] ...
ticket.py move T-0001 requests|issues|backlog|wip|completed|cancelled|obsolete [--lane NAME|-] [--blocked|--unblocked] [--note T] [--by NAME]
ticket.py migrate        # optional: write the new fields into every ticket once
```

Tickets without the new fields get defaults when read, so no migration is required.

## Deploy and operate

Ansible role `ansible/roles/tickets-board`, playbook `ansible/playbooks/tickets-board.yml`; run it from `ansible/` like any other playbook. Variables are in the role defaults (namespace, UI uid 1012, port, state and secret paths, the agent registry). The role also installs the ingest and digest timers (`watoom-tickets-ingest.timer` every two minutes, `watoom-tickets-digest.timer` daily), generates the password and tokens once and never overwrites them, and restarts the pod when the source changes.

Check it: `kubectl -n glance get pods | grep tickets-board`, `systemctl is-active watoom-tickets-board-broker`, and `curl -sk https://glance.internal.homelab.example/tickets/api/summary`.

## Known limits

- The UI uid must not belong to a host account (the broker trusts its socket peer by uid); 1011 is the host user `codex`, so 1012 is used.
- Sessions are lost when the pod restarts.
- Tests: `python3 -m unittest` in `tools/tickets/board` (`test_board.py`).
