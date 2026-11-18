# Tickets board (kanban) - design

Status: built in source (2026-11-17) and deployed live (2026-11-18, confirmed after a host reboot: broker, pod and the
rendered Glance ConfigMap all serve current data). `ticket.py` extensions, `board/` (broker, server, web, tests), the
`tickets-board` role and playbook, and the Glance widget + Hub bookmark exist and are running. Deviations from the text below:

- UI uid/gid is **1012**, not 1011: 1011 is the host user `codex`, and the broker trusts its socket peer by uid.
- `POST .../change-request/<n>`: `<n>` is the 0-based index into `change_requests`.
- An agent's move of an **unowned** ticket claims it whatever the target column (same as today's queue rule, where any
  status change by a model claims an unowned ticket); 6.2's "owner unchanged" applies to owned and shared tickets.
- The role writes `tokens.json` in place (same inode) so the running pod's single-file mount sees new tokens.
- Done 2026-11-18: `manifests/10-infrastructure/glance/glance.yml` re-rendered from `glance.yml` and applied
  (`apply-glance-with-guide.sh`); live ConfigMap and ingress confirmed serving the tickets widget.
- Still not done (content follow-up, not required for the board to work): `docs/guide/tickets.md`, the `watoom-tickets`
  skill, and `_src/shared/73_tickets.md` don't yet mention the new optional `queue`, `shared` and `move` fields/command.

Goal: a full kanban ticketing page at `https://glance.internal.homelab.example/tickets/` that the owner, the Claude Code
sessions (Sonnet, Sabre) and the local models all write to, on top of the existing store
`/data/ai/tickets/tickets.json`. The CLI (`watoom-ticket`), the `.opencode/tickets` queue + `ingest`, `digest`,
`repost` and the Discord channels keep working as they do today. Glance gets a small read-only counts widget.

Summary of the decisions:

| Area | Decision |
|---|---|
| Columns | New field `queue` (requests, issues, backlog, wip, completed, cancelled, obsolete). `status` keeps its 5 values and stays the authority; `queue` refines it |
| WIP lanes | One lane per agent. The lane is the ticket's existing `owner`. No new field |
| Override / global | One new boolean `shared`. Set at creation ("global ticket") or later by the owner (the checkbox) |
| Storage | Same file, same `Store` class, same flock. One addition: a lock-free read |
| Backend | Two stdlib files following skill-editor: `server.py` (UI pod, uid without store access) and `broker.py` (root, imports `ticket.py`) |
| Frontend | Plain HTML/CSS/vanilla JS, native HTML5 drag and drop, 10 s polling. No build step |
| Auth | Owner: password + session cookie (as skill-editor). Agents: one bearer token each. CLI and queue paths: declared names, as today |
| Migration | None required. Tickets without the new fields get defaults when read |

## 1. What was found in the live store (2026-11-17)

These facts drive several choices below.

- 53 tickets: 22 done, 19 open, 7 dropped, 3 doing, 2 blocked.
- 14 tickets have no `owner` and no `change_requests` key at all (created before those fields existed). 29 more have
  `owner: ""`. Only 10 tickets have an owner, all `model:Swift-Qwen-coder`. So 43 of 53 tickets are unowned.
- The 5 in-progress tickets: T-0006 (blocked, no owner), T-0027 (doing, no owner), T-0043 (blocked, no owner),
  T-0045 (doing, `model:Swift-Qwen-coder`), T-0049 (doing, no owner, created by `claude-sonnet-3a`).
- Names in `by` on tickets and notes: `claude` (148 notes), `root` (11), `claude-sabre-fd` (5), `claude-sonnet-3a` (3),
  `owner` (1), `model:Swift-Qwen-coder`. There is no single name per agent yet.
- Ownership is enforced only in `apply_request` (the queue path). The CLI enforces nothing: `status`, `note` and
  `assign` accept any `--by` and change any ticket.
- `Store.__enter__` takes the exclusive lock and `__exit__` rewrites the file even for `list` and `show`.
- `sync()` holds the store lock while it calls Discord (10 s timeout per call).
- `/usr/local/bin/watoom-ticket` is a copy of `ticket.py`. No role or playbook installs it or the timers
  (searched `*.yml`, `*.j2`, `*.sh` for `watoom-ticket` and `tools/tickets`); it was installed by hand.
- `/data/ai/tickets` is `root:root 0755`, the file is `0644`, the webhook files are `root 0600`.

## 2. Data model

### 2.1 New fields (all optional, all additive)

| Field | Type | Default when missing | Meaning |
|---|---|---|---|
| `queue` | string | derived from `status` (see 2.3) | The board column: `requests`, `issues`, `backlog`, `wip`, `completed`, `cancelled`, `obsolete` |
| `shared` | bool | `false` | Any agent may work this ticket (the override checkbox / the global flag) |

Nothing else changes. `id`, `title`, `body`, `status`, `priority`, `project`, `pr`, `by`, `owner`, `change_requests`,
`source`, `created`, `updated`, `notes`, `discord` keep their meaning. The top-level `{"next": N, "tickets": [...]}` is unchanged.

One value is added to an existing field: a change request `state` may now be `rejected` (today only `pending` and
`approved`). Existing code only tests `== "pending"`, so nothing breaks.

### 2.2 Why `queue` is a separate field and the status enum is not extended

Adding statuses (`request`, `issue`, `obsolete`...) breaks existing code in several places:

- `COLOURS[t["status"]]` and `ICONS[t["status"]]` in `embed()` and `digest` raise `KeyError` on an unknown status.
  `sync()` catches it and silently stops posting that ticket to Discord.
- `ACTIVE`, `MODEL_STATUSES`, `CHANNELS`, the argparse `choices`, `OPEN-TICKETS.md`, the agent prompt block
  (`_src/shared/73_tickets.md`), the `watoom-tickets` skill and `docs/guide/tickets.md` all list the 5 values.
- The installed `/usr/local/bin/watoom-ticket` is a copy. Until it is replaced it would refuse or mis-handle new values.

A separate `queue` avoids all of that. Every reader that only knows `status` still sees a valid value.

### 2.3 Rule: `status` is the authority, `queue` refines it

Each queue belongs to a set of statuses:

| `queue` | Allowed `status` | Global or per agent |
|---|---|---|
| `requests` | `open` | global |
| `issues` | `open` | global |
| `backlog` | `open` | global |
| `wip` | `doing`, `blocked` | one lane per agent (lane = `owner`) |
| `completed` | `done` | global |
| `cancelled` | `dropped` | global |
| `obsolete` | `dropped` | global |

`blocked` is not a column. A blocked ticket stays in its agent's WIP lane with a red "blocked" badge.

Reading (one function, used by everything that shows a queue):

```python
QUEUE_STATUS = {"requests": ("open",), "issues": ("open",), "backlog": ("open",), "wip": ("doing", "blocked"),
                "completed": ("done",), "cancelled": ("dropped",), "obsolete": ("dropped",)}
DEFAULT_QUEUE = {"open": "backlog", "doing": "wip", "blocked": "wip", "done": "completed", "dropped": "cancelled"}

def queue_of(t):
    q = t.get("queue")
    return q if q in QUEUE_STATUS and t["status"] in QUEUE_STATUS[q] else DEFAULT_QUEUE[t["status"]]
```

If a writer that does not know `queue` (an old `watoom-ticket` copy, a hand edit) changes `status`, the stored `queue`
no longer matches and `queue_of` falls back to the default for the new status. The board can never show a ticket in a
column that contradicts its status.

Writing:

- `Store.set_status(tid, status, ...)` (existing): after setting the status, if the stored queue does not allow it,
  set `t["queue"] = DEFAULT_QUEUE[status]`. A ticket in `issues` that goes `open -> doing -> open` lands in `backlog`.
- `Store.move(tid, queue, blocked=False, note="", by="")` (new): sets `queue`, then calls `set_status` with the
  status for that queue (`wip` gives `doing`, or `blocked` when `blocked=True`). It returns `(ticket, old_status)`
  so the caller builds the same Discord headline as today.
- `Store.add(..., queue="requests", shared=False)`: accepts `requests`, `issues` or `backlog` only. A new ticket is always `open`.

### 2.4 Migration of the 53 live tickets

None is required. With the rule above:

- 19 open tickets show in **Backlog** (they are already accepted work, not new requests).
- 5 doing/blocked tickets show in **Work in progress**: T-0045 in the Swift-Qwen-coder lane, the other four in the
  **Unassigned** lane until someone drags them to a lane.
- 22 done show in **Completed**, 7 dropped in **Cancelled**. Nothing is in Obsolete until the owner moves it.
- `shared` is `false` everywhere.
- The 14 tickets without `owner` / `change_requests` keys are read with `.get(...)`, as `ticket.py` already does.
  New code must not index `t["owner"]` or `t["change_requests"]` directly.

Optional, not needed for correctness: `ticket.py migrate` writes `queue`, `shared`, `owner: ""` and
`change_requests: []` into every ticket once, so the file is uniform. It changes no status and posts nothing to Discord.

### 2.5 Discord

No change is needed. Channels are chosen by `status`, so `requests`/`issues`/`backlog` post to `new`, `wip` to
`progress`, `completed` to `closed`, and both `cancelled` and `obsolete` to `cancelled`. A move inside the same
status (backlog -> issues) edits the one existing message in place.

Small optional addition: `embed()` adds a "Queue" field when `queue_of(t)` differs from the default for the status
(so "issues" and "obsolete" are visible in Discord), and a "Shared" field when `shared` is true.

## 3. Ownership and access rules

### 3.1 Identities

Today the same agent appears under several names. The board needs one id per agent, so add a registry file,
`/data/ai/tickets/agents.json` (root, 0644, no secrets in it):

```json
{"agents": [
 {"id": "owner",                  "label": "Owner",  "role": "owner", "lane": false, "aliases": ["root", "watoom"]},
 {"id": "claude-sonnet",          "label": "Sonnet", "role": "agent", "lane": true,  "aliases": ["claude-sonnet-3a"]},
 {"id": "claude-sabre",           "label": "Sabre",  "role": "agent", "lane": true,  "aliases": ["claude-sabre-fd"]},
 {"id": "model:Swift-Qwen-coder", "label": "Swift Qwen coder", "role": "agent", "lane": true, "aliases": []}
]}
```

- `id` is the exact string written to `owner` and `by`. Queue models keep the `model:<name>` form that `apply_request` already produces.
- `aliases` map old names to the id for display and for the ownership test. Stored history is never rewritten.
- `role: owner` is the human. There is exactly one.
- WIP lanes shown = every registry agent with `lane: true`, plus every `owner` value found on a ticket in `wip`,
  plus "Unassigned". A new model that claims a ticket through the queue gets a lane without a config change.
- The old name `claude` (148 notes, 41 tickets created) is from before the sessions had nicknames. It is left as a
  plain historical name with no lane (see open question 1).

### 3.2 The rule

`owner` keeps its meaning: the one agent accountable for the ticket, and now also its WIP lane.
`shared` is the override. One function in `ticket.py`, used by `apply_request` and by the broker:

```python
def may(actor, role, action, t):
    """True when actor may do action on ticket t. Actions: note, status, move, edit, share, assign, drop, change_request."""
    if role == "owner":
        return True
    if action in ("share", "assign", "drop"):        # drop = move to cancelled or obsolete, or status dropped
        return False
    if action == "change_request":
        return True
    owner = canonical(t.get("owner", ""))
    if t.get("shared") or owner == actor:
        return True
    return not owner and action in ("status", "move")   # unowned: the first agent to start it claims it (today's rule)
```

| Who | Own ticket | Another agent's ticket, `shared: false` | Any ticket with `shared: true` | Unowned ticket |
|---|---|---|---|---|
| Owner (human) | everything | everything | everything | everything |
| Agent | note, status, move, edit | rejected; files a `change_request` | note, status, move, edit; may take it into its own lane | may start it (claims it); note is rejected until claimed, as today |

Fixed points, same as today: only the human sets `dropped` (now: moves to Cancelled or Obsolete), assigns an owner,
or approves a change request. New: only the human changes `shared` after creation.

### 3.3 `shared` in detail

- "Global ticket" at creation: the creator sets `shared: true` (checkbox in the New ticket form, `--shared` on
  `ticket.py add`, `"shared": true` in a queue create request). `owner` is the creator for a model-created ticket,
  as today, and empty for a human-created one.
- "Override checkbox" later: a checkbox "Other agents may work on this" in the ticket detail panel. Only the human
  can tick or clear it. It writes `shared` and appends a note `shared: off -> on`.
- Taking a shared ticket: when an agent moves a shared ticket into its own WIP lane, `owner` becomes that agent and a
  note `owner changed: A -> B (shared ticket)` is appended, using the same text format as `assign`. Notes and status
  changes that do not move the lane leave `owner` alone.
- Clearing `shared` does not change `owner`. The ticket goes back to single-owner rules with whoever holds it.

### 3.4 Change requests (extended, not replaced)

An agent blocked by the rule still files a change request (queue action `change_request`, or the "Request a change"
box in the detail panel). The detail panel gives the human three buttons on each pending request:

| Button | Effect |
|---|---|
| Give ticket to `<requester>` | Exactly today's `Store.assign(tid, requester)`: owner changes, the request becomes `approved` |
| Share ticket | `shared = true`, the request becomes `approved`, owner unchanged |
| Reject | The request becomes `rejected`, with an optional note |

`ticket.py assign T-0003 <model>` keeps working unchanged.

### 3.5 Change to `apply_request` (the queue path)

Two lines of behaviour change, both additive:

- The owner test `if owner and owner != by` becomes `if not may(by, "agent", action, t)`, which lets a model work a shared ticket.
- New optional keys: `"queue"` and `"shared"` on a create request; new action
  `{"schema":1,"id":"m","action":"move","ticket":"T-0003","queue":"issues","note":"..."}` limited to
  `requests`, `issues`, `backlog`, `wip`, `completed`.

Every existing request file format is still valid and gives the same result on a non-shared ticket.

### 3.6 The CLI

The CLI runs as root on the host and can edit the file directly, so it cannot be a security boundary. Design:
leave `add`, `status`, `note`, `assign` unenforced as today (operator path), and add `move` and `--shared`.
The two Claude Code sessions use the CLI with their registry id: `--by claude-sonnet`, `--by claude-sabre`.
Whether the CLI should apply `may()` when `--by` is a registered agent is open question 3.

## 4. API

### 4.1 Processes

Same split as skill-editor:

- `tools/tickets/board/server.py` - the UI pod. Serves the static files and the HTTP API, does authentication, Origin
  and CSRF checks, then forwards one JSON line per request over a Unix socket. It has no access to the store or the webhooks.
- `tools/tickets/board/broker.py` - root systemd service. Accepts only the UI uid (`SO_PEERCRED`, as
  `skill-editor/broker.py` line 129), imports `ticket` and performs every operation through `Store`, `may()` and `sync()`.
  It never trusts a ticket field from the UI beyond the documented inputs; it receives `actor` and `role` from the server.

The broker is needed because the store is root-owned and the Discord webhook files are root-only. Mounting them
into a pod would give the pod the webhook URLs.

### 4.2 HTTP endpoints (all under the prefix `/tickets`)

| Method and path | Body | Result |
|---|---|---|
| `GET /api/session` | - | `{"actor":"owner","role":"owner","csrf":"..."}` |
| `GET /api/board` | - (`If-None-Match` supported) | `{"etag":"...","queues":[...],"lanes":[{"id":"claude-sonnet","label":"Sonnet"},...],"tickets":[card...]}` or `304` |
| `GET /api/tickets/T-0049` | - | the full ticket plus `"queue"` (computed) and `"can": {"move":true,"note":true,"edit":true,"share":false,"drop":false}` |
| `POST /api/tickets` | `{"title","body","project","priority","queue","shared"}` | `{"ticket":"T-0054","duplicate":false}` |
| `POST /api/tickets/T-0049/move` | `{"queue":"wip","lane":"claude-sabre","blocked":false,"note":"","if_updated":"2026-11-17T17:32:10Z"}` | the updated card |
| `POST /api/tickets/T-0049/note` | `{"text":"..."}` | the updated ticket |
| `POST /api/tickets/T-0049/edit` | any of `{"title","body","priority","project","pr","shared","owner"}` plus `if_updated` | the updated ticket |
| `POST /api/tickets/T-0049/change-request` | `{"text":"..."}` | the updated ticket |
| `POST /api/tickets/T-0049/change-request/2` | `{"decision":"assign"|"share"|"reject","note":""}` | the updated ticket (owner only) |
| `GET /api/summary` | - | counts only, see 6.4. No titles, no text |

A card is the ticket without `body`, `notes`, `change_requests`, `source`, `discord`, plus `queue`, `lane`,
`note_count`, `pending_requests` and the last note time. With 53 tickets the whole board is a few kilobytes.

Errors: `400` bad input, `401` not signed in, `403` Origin/CSRF or `may()` refused (body says who owns the ticket and
suggests a change request, same wording as the queue rejection), `404` no such ticket, `409` the ticket changed since
`if_updated`.

Limits reuse the existing ones: title 200, body 4000, note 1000, project 80, pr 300, request body 16 KB.

### 4.3 What the broker does for each write

```
with Store() as s:                      # exclusive flock, read, modify
    t = s.find(tid)
    check may(actor, role, action, t)   # 403 on refusal
    check t["updated"] == if_updated    # 409 on mismatch, when if_updated was sent
    t, old = s.move(...) / s.note(...) / ...
                                        # __exit__: atomic replace, unlock
queue sync(t["id"], headline) on one background worker thread
reply with the updated ticket
```

`edit` of `title`/`body`/`priority`/`project` appends a note such as `title changed` so the history shows it.
Changing `owner` through `edit` is `Store.assign`. Changing `shared` appends its note.

### 4.4 Is the existing flock enough?

Yes for writes. The CLI, `ingest` and the broker all go through `Store`, which holds one exclusive lock for the whole
read-modify-write and replaces the file atomically. Three writers on one host and one local filesystem is the case it was built for.

Three things to change or respect:

1. **Lock-free reads (new).** `Store` rewrites the file on every `with` block, including reads. The board polls, so
   reads must not take the lock or rewrite the file. Add:

   ```python
   def load(directory=None):
       """Read-only snapshot. Safe without the lock because writers replace the file atomically."""
       p = (pathlib.Path(directory) if directory else tickets_dir()) / "tickets.json"
       return json.loads(p.read_text()) if p.exists() else {"next": 1, "tickets": []}
   ```

   `GET /api/board`, `GET /api/tickets/<id>` and `GET /api/summary` use `load()`. The board `etag` is the file's
   `st_mtime_ns` and `st_size`, so an unchanged poll is one `stat` and a `304`.

2. **Discord calls hold the lock.** `sync()` keeps the store locked during its HTTP calls, and `repost` does that
   once per ticket. A browser move issued during a slow Discord call waits up to about 10 s. The broker therefore
   answers the browser as soon as the store write is done and runs `sync()` on a single background thread.
   Changing `sync()` to release the lock around the network call is a possible later improvement, not part of this design.

3. **Lost updates between people.** The lock orders writes but does not stop a stale browser overwriting a newer
   change. Every UI write sends `if_updated`; the broker refuses with `409` when the ticket's `updated` differs and the
   UI reloads that card. `updated` has one-second resolution; two changes to the same ticket in the same second can
   slip through, which is acceptable here (the result is still a valid ticket and both notes are kept).

One file, one module: the role installs the same `ticket.py` to `/usr/local/bin/watoom-ticket` and next to
`broker.py`, in one task, so the CLI, the timer and the broker never run different versions.

## 5. Authentication

| Writer | How it writes | How it is identified | Strength |
|---|---|---|---|
| Owner (human) | Browser on `/tickets/` | Password login, then an `HttpOnly; SameSite=Strict; Secure` session cookie; Origin + CSRF on every POST. Same code path as `skill-editor/server.py`. Actor `owner`, role `owner` | Real: password file readable only by the UI gid |
| Claude Code sessions (Sonnet, Sabre) | `watoom-ticket ... --by claude-sonnet` (CLI, as today). Optionally the HTTP API with their token | Declared `--by`; or bearer token | Declared. They run as root on the host and could read any file, so no scheme can separate them from each other |
| Local sandboxed models | Request files in `.opencode/tickets/`, applied by `ingest` (unchanged) | `"model"` in the request, default the project folder name, stored as `model:<name>` | Declared, limited to what `apply_request` allows |
| An agent that can make HTTP calls but has no host shell (a worker on another machine, a future pod) | `Authorization: Bearer <token>` on the API | Token looked up in the token file; actor = that agent's id, role `agent` | Real, per agent |

Files (created once by the role, never overwritten, same tasks as the skill-editor password):

- `/data/ai/private/tickets-board/password` - owner password, `root:<ui gid> 0640`, at least 24 characters.
- `/data/ai/private/tickets-board/tokens.json` - `{"<sha256 of token>": "<agent id>"}`, `root:<ui gid> 0640`. The pod
  only ever sees hashes.
- `/data/ai/private/tickets-board/tokens/<agent id>` - the plain token for that agent, `root 0600`, for handing to the agent.

Rules in the server:

- A bearer token never yields role `owner`. Only the password login does.
- Cookie requests need `Origin == https://glance.internal.homelab.example` and the CSRF header on POST. Bearer requests
  need neither (no browser involved) and must not carry a cookie.
- `actor` and `role` are decided by the server from the credential. A client-supplied `by` is ignored.
- Sessions last 12 h (skill-editor uses 1 h; a board is left open all day) and are held in memory, so a pod restart signs the owner out.

This is identification for a household lab, not isolation: anything with a root shell on the host can write the
store directly. The design states that rather than hiding it.

## 6. UI

### 6.1 Board layout

One page, horizontal scroll when narrow. Left to right:

```
+----------+--------+---------+--------------------------------+-----------+-----------+----------+
| Requests | Issues | Backlog | Work in progress               | Completed | Cancelled | Obsolete |
| (global) |(global)|(global) |  Sonnet            [2]         | (global)  | (global)  | (global) |
|          |        |         |   [T-0049] [T-0027]            | newest 20 | collapsed | collapsed|
| [card]   | [card] | [card]  |  Sabre             [0]         | [card]    |    7      |    0     |
| [card]   |        | [card]  |   (drop here)                  | [card]    |           |          |
|          |        | [card]  |  Swift Qwen coder  [1]         | show all  |           |          |
|          |        |         |   [T-0045]                     |           |           |          |
|          |        |         |  Unassigned        [2]         |           |           |          |
|          |        |         |   [T-0006 blocked] [T-0043 b.] |           |           |          |
+----------+--------+---------+--------------------------------+-----------+-----------+----------+
```

- Global queues: Requests, Issues, Backlog, Completed, Cancelled, Obsolete. One list each, all agents and the owner see the same cards.
- Per agent: only Work in progress. It is one wide column split into stacked lanes, one per agent from 3.1, then "Unassigned".
- Meaning of the three intake queues: **Requests** = new asks nobody has triaged (default for a new ticket);
  **Issues** = something is broken; **Backlog** = accepted and ready to be picked up.
- Order inside a list: priority (high first), then most recently updated. There is no manual ordering in the first version (open question 6).
- Completed shows the newest 20 with "show all". Cancelled and Obsolete are narrow collapsed columns showing a count;
  they expand on click and accept drops while collapsed.
- Top bar: project filter (game, homelab, esp32, ...), text filter (id and title), "mine only" toggle, **New ticket** button, signed-in name.

Card: id, title (2 lines), priority colour stripe, project chip, owner label, badges: `blocked`, `shared`,
note count, pending change requests. Status colours reuse `COLOURS` from `ticket.py` (blue, amber, red, green, grey).

### 6.2 Drag and drop

Native HTML5 drag and drop (`draggable="true"`, `dragstart`, `dragover`, `drop`). No library. On drop the UI moves
the card at once, sends `POST .../move`, and puts the card back with a message if the answer is `403` or `409`.
Columns the actor may not drop into are dimmed while dragging (from the ticket's `can` flags).

What a drop writes:

| Drop target | `queue` | `status` | `owner` | Who may |
|---|---|---|---|---|
| Requests, Issues, Backlog | that queue | `open` | unchanged | owner; the owning agent; any agent if shared |
| An agent's WIP lane | `wip` | `doing` (stays `blocked` if it was blocked and came from another lane) | that agent | owner: any lane (this is `assign`). Agent: only its own lane, and only when it owns the ticket, the ticket is unowned, or it is shared |
| Unassigned WIP lane | `wip` | `doing` | cleared | owner only |
| Completed | `completed` | `done` | unchanged | owner; the owning agent; any agent if shared. The UI asks for the "how it was verified" note and an optional PR/commit link |
| Cancelled | `cancelled` | `dropped` | unchanged | owner only. The UI asks for a reason note |
| Obsolete | `obsolete` | `dropped` | unchanged | owner only. The UI asks for a reason note |

Every move appends the standard note when text was given and produces the usual Discord headline (`open -> doing (claude-sabre)`).
A move within the same status (Backlog -> Issues, Cancelled -> Obsolete) appends a note `queue: backlog -> issues`.

Touch screens: HTML5 drag and drop does not fire on most phones. The detail panel has a "Move to" select that
calls the same endpoint, so the board is fully usable without dragging.

Refresh: the page polls `GET /api/board` with `If-None-Match` every 10 s and when the tab regains focus, and skips
the redraw while a drag is in progress. A CLI or queue change shows up within 10 s (queue requests still wait for the 2 minute ingest timer).

### 6.3 Ticket detail panel

Clicking a card opens a side panel (right, about 520 px; full screen on a phone). The URL becomes `/tickets/#T-0049` so a ticket can be linked from Discord or a note.

| Section | Content |
|---|---|
| Header | id, title (editable), status badge, queue name, "Move to" select |
| Fields | priority (select), project (text with existing projects suggested), owner (select from the registry; owner role only), PR / commit link (clickable), created by, created, updated, source (queue file path when there is one) |
| Sharing | Checkbox "Other agents may work on this" (enabled for the owner role only), and a "blocked" toggle while the ticket is in WIP |
| Body | The ticket body as preformatted text, editable |
| Updates | The `notes` list, newest first: time, author label (alias mapped), text. Status and owner changes are already notes. A text box "Add update" |
| Change requests | Each request: time, requester, text, state. Pending ones show the three buttons from 3.4 to the owner. Other agents see a "Request a change" box instead of the edit controls |

All text is inserted with `textContent`, never `innerHTML`. Titles, bodies and notes come from models. The page
keeps the skill-editor CSP (`default-src 'self'; script-src 'self'; frame-ancestors 'self'`).

Controls the actor may not use are disabled, driven by the `can` object from the API; the broker enforces the same rule regardless.

### 6.4 Glance widget

Read-only counts on the Home page (or Command Center), using the `custom-api` widget type already used throughout
`glance.yml`. It reads `GET /api/summary`:

```json
{"queues": {"requests": 0, "issues": 0, "backlog": 19, "wip": 5, "completed": 22, "cancelled": 7, "obsolete": 0},
 "blocked": 2, "high_open": 4, "pending_change_requests": 0,
 "lanes": [{"label": "Sonnet", "count": 0}, {"label": "Swift Qwen coder", "count": 1}, {"label": "Unassigned", "count": 4}],
 "updated": "2026-11-17T17:32:10Z"}
```

Sketch of the widget (template syntax to be checked against the existing `custom-api` blocks when it is built):

```yaml
- type: custom-api
  title: Tickets
  title-url: https://glance.internal.homelab.example/tickets/
  cache: 1m
  url: http://tickets-board.glance.svc.cluster.local:8789/tickets/api/summary
  template: |
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;text-align:center">
      <div><div class="size-h3 color-highlight">{{ .JSON.Int "queues.requests" }}</div><div class="size-h6">Requests</div></div>
      <div><div class="size-h3 color-highlight">{{ .JSON.Int "queues.issues" }}</div><div class="size-h6">Issues</div></div>
      <div><div class="size-h3 color-highlight">{{ .JSON.Int "queues.backlog" }}</div><div class="size-h6">Backlog</div></div>
      <div><div class="size-h3 color-highlight">{{ .JSON.Int "queues.wip" }}</div><div class="size-h6">In progress</div></div>
    </div>
    <p class="size-h6">{{ .JSON.Int "blocked" }} blocked - {{ .JSON.Int "pending_change_requests" }} change requests waiting</p>
```

Glance fetches this from inside the cluster, so the summary endpoint has no login. It returns numbers and agent
labels only (open question 5). Add a "Tickets board" bookmark on the Hub page next to "Skill Editor". The full board
can also be embedded as a Glance page with `type: iframe`, the way Command Center is; it is the same origin, so the
session cookie and `frame-ancestors 'self'` both work.

## 7. Deployment

A new role `ansible/roles/tickets-board/`, a copy of the skill-editor role's structure, and a playbook
`ansible/playbooks/tickets-board.yml` shaped like `skill-editor.yml`.

Source layout:

```
tools/tickets/ticket.py              existing; gains queue_of, may, load, Store.move, add(queue, shared), migrate
tools/tickets/test_ticket.py         existing; new cases for the rules above
tools/tickets/board/server.py        UI pod (stdlib)
tools/tickets/board/broker.py        root broker (stdlib, imports ticket)
tools/tickets/board/test_board.py    unittest, same style as test_skill_editor.py
tools/tickets/board/web/index.html login.html app.js style.css
```

`defaults/main.yml` (values to confirm free on the host before use):

```yaml
tickets_board_namespace: glance
tickets_board_uid: 1011                    # skill-editor uses 1010
tickets_board_gid: 1011
tickets_board_origin: https://glance.internal.homelab.example
tickets_board_prefix: /tickets
tickets_board_port: 8789                   # skill-editor uses 8788
tickets_board_image: <same pinned python digest as skill_editor_image>
tickets_board_app_root: /app/tickets-board
tickets_board_state: /data/ai/helper-scripts/state/tickets-board
tickets_board_socket_dir: /data/ai/helper-scripts/state/tickets-board/socket
tickets_board_private_dir: /data/ai/private/tickets-board
tickets_board_service_name: watoom-tickets-board-broker
tickets_board_store_dir: /data/ai/tickets
tickets_board_agents_file: /data/ai/tickets/agents.json
tickets_board_agents: [...]                # the registry from 3.1; the role renders agents.json from it
```

Tasks, in the order skill-editor uses:

1. Refuse to replace a `tickets-board` Deployment that is not labelled `watoom.io/owner: tickets-board`.
2. Copy the source to the app root. Copy `ticket.py` there and to `/usr/local/bin/watoom-ticket` (0755) in the same task.
3. Install the four existing timer/service units from `tools/tickets/` (today installed by hand). Do not change their schedule.
4. Create state, socket dir (`root:<gid> 0750`), private dir; generate the password and one token per agent once (`creates:`, `no_log`).
5. Render `agents.json`, `tokens.json` and the broker `config.json`.
6. Install and start `watoom-tickets-board-broker.service` (copy of `broker.service.j2`: root, `NoNewPrivileges`, `MemoryMax=256M`, `Restart=on-failure`), flush handlers.
7. Fingerprint the source, render and apply `resources.yml`: Deployment (non-root uid, read-only root filesystem, all capabilities dropped,
   hostPath mounts for app (read-only), password and tokens.json (read-only), socket), Service, and a Traefik `IngressRoute`
   `Host(glance.internal.homelab.example) && PathPrefix(/tickets/)`, priority 110, TLS secret `watoom-tls`.
8. `kubectl rollout status`.

The pod mounts neither `/data/ai/tickets` nor `/data/ai/secrets`.

Follow-up edits when it is built (not part of the role): the Glance widget and bookmark in `config/glance/glance.yml`,
`docs/guide/tickets.md`, the `watoom-tickets` skill and `_src/shared/73_tickets.md` (new optional `queue`, `shared`, `move`).

Suggested build order, each step usable on its own:

1. `ticket.py`: `queue_of`, `may`, `load`, `Store.move`, `shared`, CLI `move`/`--shared`, queue `move`, tests. No UI yet; the CLI already shows queues.
2. Broker + server + read-only board (no drag).
3. Writes: move, note, create, edit, change-request decisions.
4. Role, playbook, Glance widget, docs.

## 8. Open questions for the owner

1. **Agent list and names.** Which lanes exist on day one? Proposed: Sonnet (`claude-sonnet`), Sabre (`claude-sabre`),
   Swift Qwen coder (`model:Swift-Qwen-coder`), Unassigned. Are the short ids acceptable in place of `claude-sonnet-3a` /
   `claude-sabre-fd`? What should the old shared name `claude` map to: nothing (proposed), or one of the sessions?
2. **Where existing tickets land.** Proposed: all 19 open tickets in Backlog, and the four unowned in-progress tickets
   (T-0006, T-0027, T-0043, T-0049) in Unassigned for you to drag to a lane. Alternative: a one-off backfill that assigns
   them from the note authors.
3. **Should the CLI enforce ownership?** Today it does not, and Sonnet and Sabre both use it. Options: leave it open
   (proposed; the board and the queue enforce, the CLI is the operator path), or apply `may()` whenever `--by` is a
   registered agent and add `--force` for you. Either way it is a convention, not security, because the sessions run as root.
4. **Who may tick "shared"?** Proposed: anyone at creation, only you afterwards. Alternative: the owning agent may also
   release its own ticket.
5. **Summary endpoint without login.** It exposes only counts and agent labels on the internal network. If that is not
   acceptable, the widget must send a token header and the count stays out of unauthenticated reach.
6. **Manual ordering.** Dragging a card up or down inside a column does nothing in this design (sorted by priority, then
   time). Real ordering needs a `rank` number per ticket and reorder writes. Wanted?
7. **Obsolete vs Cancelled in Discord.** Both post to the `cancelled` channel. A separate channel needs one more webhook
   file (`_obsolete`) and one line in `CHANNELS` handling.
8. **May agents propose Cancelled/Obsolete directly?** Proposed: no, they file a change request and you move it
   (matches "models cannot set dropped" today).
9. **Default queue for new tickets.** Proposed: Requests for everything new, including queue-created model tickets and
   `watoom-ticket add`. Alternative: model-created tickets go to Issues, since models mostly log problems they found.
10. **Unowned-ticket notes.** Today a model's note on an unowned ticket is rejected ("start it to claim it"). 43 of 53
    tickets are unowned, so on the board most cards will refuse agent notes until claimed or shared. Keep, or allow notes on unowned tickets?
11. **Blocked as a badge, not a column.** A blocked ticket stays in its agent's lane. If you want a visible global
    "Blocked / waiting on owner" column instead, it is one more `queue` value mapped to status `blocked`.
12. **Phone use.** Drag and drop will not work on a phone; the "Move to" select covers it. A touch drag library would
    break the no-dependency rule, so it is left out unless you ask for it.

Not verified in this design and to be checked at build time: that uid/gid 1011 and port 8789 are free, the exact
Glance `custom-api` template functions for nested keys, and that the installed `/usr/local/bin/watoom-ticket` matches the current `ticket.py`.

## 9. Owner decisions (2026-11-17)

1. Short ids (`claude-sonnet`, `claude-sabre`), `claude` maps to nothing. **Amendment: the local-model lane list in
   3.1 must stay generic, not hardcoded to one name** -- the owner runs a number of local models over time, not just
   Swift-Qwen-coder. 3.1 already does this correctly (any `model:<name>` that claims a ticket gets a lane with no
   config change; `agents.json` only seeds day-one labels) -- keep it that way, do not special-case one model id in
   the UI or broker code.
2. All open tickets to Backlog; the 4 unowned in-progress ones to Unassigned. No backfill-assign script.
3. Leave the CLI ownership-unenforced, as today. No `--force` flag added.
4. Anyone may set `shared` at creation; only the owner may change it afterwards.
5. Glance counts widget: no login required.
6. No manual `rank`/reorder field. Sort by priority then time.
7. Obsolete and Cancelled share the existing `cancelled` Discord channel. No new webhook.
8. Agents may not move a ticket to Cancelled/Obsolete directly; change request only.
9. New tickets default to the Requests queue regardless of source.
10. Keep the "claim before note" rule for unowned tickets.
11. Blocked stays a badge on the card, in the owner's lane. No separate Blocked column.
12. Phone fallback is a "Move to" `<select>`; no touch-drag dependency added.
