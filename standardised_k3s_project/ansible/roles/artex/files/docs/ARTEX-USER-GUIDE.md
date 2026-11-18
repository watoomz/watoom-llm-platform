---
title: Artex user guide
nav: Artex
summary: How to use the Artex autonomous security-testing console deployed in this homelab — tasks, the asset/exploration graph, the intercept approval gate, findings, traffic recording and this deployment's own hardening.
---

> [!WARNING]
> Artex is an autonomous agent that executes shell commands, drives a real browser and sends network
> traffic on your behalf. Use it only against systems you own or have explicit written authorization to
> test. This deployment does not change that: it only constrains where Artex can run and who can reach it.

## What this is

[Artex](https://github.com/RuoJi6/ARTEX) is an open-source, LLM multi-agent autonomous penetration-testing
harness (Go backend, embedded Next.js frontend, PostgreSQL). This homelab runs the **FailSafe** hardened
fork, built from audited source after the upstream `tomicdd/artex` Docker image was found to contain an
unauthenticated command-execution backdoor in November 2026 — see `ansible/vars/artex.yml` for the pinned
image digest and the review process for updating it.

Full downloadable copy of this guide: [artex-user-guide.pdf](/guide/assets/artex-user-guide.pdf).

## Opening the console

- URL: `https://artex.internal.homelab.example` (internal only, via Traefik; there is no path from outside the
  homelab network).
- First visit goes to `/setup` to create the admin password. After that, sign in at `/login`.
- If you left the LLM key blank at setup, configure a provider under **System → LLM** before starting a
  task — see [Pointing it at a model](#pointing-it-at-a-model) below.

## Core concepts

Artex separates **what you're trying to find out** from **what you've already confirmed exists**, as two
linked graphs:

| Graph | Scope | Nodes | Purpose |
|---|---|---|---|
| **Exploration graph** | Per task | `goal` → `intent` → `fact` / `finding` / `hint` | The reasoning trail for one run: which direction produced which evidence |
| **Asset graph** | Shared across all tasks | `root_domain` → `subdomain` → `service` → `endpoint` | The accumulated ground truth about what exists, reused by later tasks |

An **anchor** ties exploration-graph nodes to the asset-graph nodes they touched, which is what powers the
asset coverage view (which assets have been tested, by which task, with what result).

Three agent roles do the work:

- **planner** — the only agent that creates intents. It reads the exploration graph's current state and, when
  there is an uncovered direction, issues 0 or more intents. It keeps a **shared todolist** across its own
  wake-ups so a multi-step attack chain (find an injection point → get credentials → pivot → escalate) is
  pursued in dependency order across many planning rounds instead of being flattened into one pass.
- **worker** — claims one intent, runs real tools against the target, and writes facts / assets / findings
  back to the graphs, then stops. Several workers run concurrently per task (configurable, default 3). A
  worker can search other workers' raw execution traces for this task (`search_all_worker_traces`) to reuse
  an observation that was never promoted to a formal fact, without crossing into another worker's intent.
- **mainagent** — the human-in-the-loop chat agent (the **Chat** page) for direct Q&A, steering a task, or
  pulling it off its default path.
- **retester** — a separate, editable agent (prompt, LLM, budget, tools configurable under **System →
  Agents**) that reruns a specific finding to check whether a fix actually worked. Started from a finding's
  row or detail page; its conclusion (`still reproducible` / `fixed` / `could not confirm`) can set the
  finding's status automatically.

## Creating and running a task

**Function → Tasks → New task**. Fields that matter beyond the obvious name/description/goal:

| Field | Effect |
|---|---|
| **LLM profile(s)** | Which configured model(s) run this task; omit to use the system's active default. Multiple profiles form an ordered chain — the first is used until you switch it (useful for starting cheap and escalating). |
| **Timeout** (`timeout_seconds`) | A wall-clock budget for the whole task, starting from its *first* run, not from creation. `0`/blank = unlimited. When it elapses the task enters wrap-up: in-flight intents get a short drain grace period to finish cleanly, and anything still running past that is hard-cancelled and the task is marked `timeout`. **If a task times out but the work clearly needed more time, just rerun it with a longer or unlimited budget** — nothing was broken, the budget simply ran out mid-round. |
| **Plan heartbeat** (`plan_heartbeat_seconds`) | How often the planner re-evaluates even with no new facts (default and floor: 600s / 10 min). Lower it for a task you're actively watching; there's no benefit to lowering it below the time your workers actually take. |
| **Seed first intent** | Skip the first planning round and hand the worker a seed intent immediately (built from the goal/description). Useful for a narrow, already-well-understood target (e.g. a CTF box) where you don't need the planner's first pass. |
| **Coverage** | Whether asset-coverage tracking/display and automatic scope accumulation are on for this task (default on). Turning it off also hides `add_task_scope`/`list_untested_assets` from the agent — only turn it off if you specifically don't want the task touching the shared asset graph's scope. |
| **Associated companies** | Snapshot-links the task to existing company/asset scope without copying assets or forcing intents — the planner can see and choose to use them. |
| **Source tasks** | Read-only inheritance from earlier tasks (up to the configured max) — lets a follow-on task see prior findings/facts without rediscovering them. |
| **Task-level intercept rules** | Extra allow/deny/ask rules that apply only to this task, on top of the global rules below. |

A task's lifecycle is event-driven, not polled: a graph change wakes the planner, the planner issues intents
into a frontier queue, a free worker claims the next one, executes it for real (through the recording proxy,
see below), writes results back — which wakes the planner again. Most wake-ups issue **zero** new intents;
that's the planner deciding there's nothing uncovered yet, not a stall.

## Where the results show up

- **Findings** (`Function → Findings`) — flat list, grouped-by-task, or asset view. Each has a retest action;
  see [Retesting a finding](#retesting-a-finding).
- **Assets** (`Function → Assets`) — the shared asset graph; the force-directed **coverage graph** highlights
  what's been tested and lets you collapse/expand by node.
- **Traffic** (`Function → Traffic`) — every HTTP(S) request/response a worker made, captured by the
  MITM recording proxy with CA-verified provenance (not just a passive sniff).
- **Workspace** (`Function → Workspace`) — files a task's tools produced.
- **Commands** (`Function → Commands`) — the raw shell/tool calls a task ran.
- **LLM records** (`Function → LLM records`) — token/cost accounting per task, per lane (planner / worker /
  mainagent / the intercept judge, see below).

## Retesting a finding

From a finding's row, its detail page, or the task's **Retest** tab: pick the finding, optionally note the
claimed fix version or test conditions, and start a retest. It runs as its own agent session (the
`retester` agent, configurable under **System → Agents**) — it does **not** restart or reuse the original
scanning task. While it runs you'll see a spinner and "retesting"; the conclusion (`still reproducible`,
`fixed`, `could not confirm`) is saved on the finding with its evidence and a link back to the retest
session. A `fixed` conclusion automatically updates the finding's status; any other conclusion leaves it
alone (you can still set the status by hand from the dropdown). If a retest is already running for a
finding, re-triggering it reuses that same run rather than starting a second one.

## The intercept approval gate — the actual safety control

**System → Intercept** is the one setting that determines whether Artex can act without you watching. Every
tool call a worker/planner/mainagent wants to make is checked, in priority order (highest first), against
your rules before it runs:

| Match target | What it matches | Match type |
|---|---|---|
| `tool_name` | Which tool is being called (e.g. a shell runner, an HTTP request tool) | exact string or regex |
| `tool_input` | The actual content of the call (a command line, a URL, a payload) | exact string or regex |

Each rule's **action** is one of:

- **allow** — let it through immediately, skip lower-priority rules.
- **deny** — block it and hand the model a message explaining why (the rule's `message` field), so it can
  try a different approach instead of just failing silently.
- **ask** — block it, create a pending approval, surface it inline in that task's activity stream and in
  the global pending-approvals list, and wait for you to approve or deny. An `ask` rule can also carry a
  timeout with its own fallback action (allow or deny) if nobody responds in time.

> [!RULE]
> A tool call that matches **no** rule at all is not silently allowed: it falls through to an LLM **judge**
> (a configured model, defaulting to the active profile) that reviews the call and returns a verdict with a
> reason. The judge's own default behaviours are configurable (`System → Intercept` → judge settings):
> what happens if the judge call itself fails, and what the fallback is if an `ask`-style judge verdict times
> out. Judge usage is billed and tracked separately under LLM records (the `judge` lane), apart from the
> planner/worker/mainagent lanes.

Approve or deny a pending call either from the global pending-approvals list or inline in the task's chat/
activity view where it appeared — both views show the same record.

## Traffic recording

Every Bash and HTTP action a worker takes is recorded, not just logged: the proxy is a MITM man-in-the-middle
with its own CA, so HTTPS traffic is decrypted for the recording rather than just captured as opaque bytes.
In this deployment the proxy (`:8788` upstream) is **not** exposed outside the pod — only the console
(`artex`, port 8787 internally, published at `artex.internal.homelab.example`) has an ingress route at all; see
[This deployment's specific hardening](#this-deployment-s-specific-hardening).

## Pointing it at a model

**System → LLM** manages one or more named profiles (provider, model, base URL, key). This deployment's
default profile points at the homelab's own OpenAI-compatible **llm-router** (`llama-cpp` namespace, port
8000) rather than an external provider — no request from Artex reaches a third-party LLM API unless you
explicitly add and select a profile that does. The intercept judge, the retester agent, and the mainagent
chat can each be pinned to a different profile than the one driving planner/worker if you want a cheaper or
more cautious model doing judgement than doing the actual exploration.

## Skills

**System → Skills** lists what's installed; `skills/` on disk is one subdirectory per skill, each with a
`SKILL.md`. This deployment ships three: `api-recon` (frontend/API surface discovery — explicitly scoped to
recon, not exploitation), `playwright-cli` (browser automation for anything JS-rendered), and `scopesentry`
(syncing scope/assets from a ScopeSentry instance via its MCP endpoint, under **Function → Sync**, instead of
re-collecting what's already known there).

> [!WARNING]
> A skill is not sandboxed guidance text — it can instruct the agent to run arbitrary commands. Review any
> skill before adding or mounting it, the same way you'd review a new tool.

## This deployment's specific hardening

Beyond what upstream Artex and the FailSafe build already do (loopback-bound console, unpublished recording
proxy, pinned-digest base images, compiled-off self-update — see `SECURITY.md` in the Artex source), this
homelab's Ansible role (`ansible/roles/artex/`) adds:

- **Isolated namespace** (`artex`), applied and verified by the role itself: the image digest is pinned in
  `ansible/vars/artex.yml` and the role **fails closed** if that pin is missing — there is no path where a
  freshly-built image gets deployed without a human reviewing the diff and updating the pin first.
- **Ingress locked to Traefik only**: a deny-all `NetworkPolicy` on the `artex` pod, with a single explicit
  exception for the in-cluster Traefik pod on the console port. There is no other way into the console or
  the proxy, even from elsewhere in the cluster.
- **Egress to the local LLM router is the only other declared network path**: the `llama-cpp` namespace
  carries a matching `NetworkPolicy` that only accepts connections from the `artex` app pod. General
  outbound egress (to the actual targets you authorize Artex to test) is otherwise unrestricted by cluster
  policy — that's necessary for the tool to do its job, so authorization scope is enforced by what you tell
  the agent to target and by the intercept rules above, not by a firewall.
- **The Service stays `ClusterIP`**, and the role actively refuses to apply if anything in the namespace is
  exposed any other way (`NodePort`/`LoadBalancer`).
- **Private, isolated application storage**: `/data/ai/artex/{data,keys,pgdata}` on the host, each `0700`
  and SELinux-labelled `container_file_t`, owned by root except `pgdata` which is owned by the Postgres
  container's own uid/gid (70). Back these up together — losing `keys` invalidates existing sessions, losing
  `pgdata` loses every task, finding and the asset graph.
- **Database credentials are generated once**, in-cluster, and never touch Git or Ansible output.

## Operating it from this repo

```bash
# deploy / update (after reviewing and re-pinning ansible/vars/artex.yml if the image changed)
ansible-playbook -i inventories/homelab playbooks/artex.yml

# health
kubectl -n artex get pods,svc,networkpolicy
kubectl -n artex logs deploy/artex --tail=100
kubectl -n artex logs deploy/artex-postgres --tail=100

# confirm the console path end to end
curl -sk -o /dev/null -w "%{http_code}\n" https://artex.internal.homelab.example/
```

A failed deployment is a result to read, not a reason to loosen the role's assertions (the fail-closed image
pin, the `ClusterIP`-only check, the namespace/path asserts at the top of `tasks/main.yml`) — fix the actual
cause (usually: the image pin in `ansible/vars/artex.yml` is stale or missing) and rerun.
