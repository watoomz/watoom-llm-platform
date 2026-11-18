# WatooM-Code learning loop — design for owner review

Status: **phases 2–4 implemented; the nightly curator is OFF by default.** The owner's direction was
"you choose the best option for the 5 questions, it should automatically improve but have a way to roll
back or fix." Section 6 records the decisions taken under that direction. One safety line is held even
under "automatic": the loop auto-applies only to the reversible sidecar lesson layer — **never**
unattended to code, the harness, the coordinator guard, or AgentMemory itself (those stay owner-gated;
that gate is the ultimate "fix").

Source: Atai Barkai, *"Self Learning for Agents Clearly Explained"* (2026-06-24), plus the owner's
pasted notes. Supporting reading referenced by the owner: Letta sleep-time-compute and continual-learning,
OpenClaw "dreaming", Nous Hermes agent self-evolution, kayba-ai agentic-context-engine (skillbook
counters), arxiv 2606.09498 (Self-Harness), and the LangChain harness/loop-engineering posts.

## 1. Goal

Let WatooM-Code get better at WatooM's own work over time — fewer repeated mistakes, more of the owner's
preferences applied without being restated — **without** ever letting the agent silently rewrite itself,
grade its own work, or promote an unproven change. Every durable change stays gated behind the existing
owner-approved promotion path.

## 2. What already exists (we build on this, we do not replace it)

The `tools/watoom-code/self_learning/` engine already implements guarded **skill self-optimisation**:

- Structural skill-revision proposals are generated, but **originals and fenced content are preserved and
  a new revision is never written over an active file** (`optimise.py`, `optimisation.mjs`).
- **Graders sit outside the agent's reach.** Protected evaluator suites are pinned by SHA in
  `evaluator-registry.json` and run as UID 1001 with read-only system paths, private network/devices and a
  bounded writable output dir (`evaluate_existing.py`). Models cannot register, modify or run evaluators.
- Promotion needs **three independent verified sessions**, complete registered-case coverage, no safety /
  correctness / measured-cost regression, and at least one measured benefit. Byte reduction alone cannot
  pass. Unknown cases stay *pending*, not *passed*.
- **Selection is idle-gated and operator-owned**: a held native gate, zero active sessions, an exact
  revision-ID allowlist, rollout only under the existing maintenance/deployment owner, automatic rollback
  on regression. An independent systemd recovery timer never depends on the agent.
- **Usage / failure / repeated-call fingerprints** and verification receipts are already tracked per skill.

This engine already satisfies most of the article's hard safety requirements. The new work is three
*additional* loops layered on the same guardrails, plus a richer memory model.

## 3. The three new components

### 3.1 Verification loops in the harness (phase 2 — lowest risk) — **IMPLEMENTED**

Delivered as `tools/watoom-code/verification_loop.py` (tests in
`tools/watoom-code/tests/test_verification_loop.py`): a harness-run, read-only, non-mutating grader
orchestrator. It selects graders by file type over a changeset (working-tree changes or explicit `--path`),
runs them, and emits a JSON verdict (overall + per-file + per-grader, with the grader output a fix needs)
and exit 0/1. Active graders: `ansible-lint` (the repo's `.ansible-lint` authority) and
`ansible-playbook --syntax-check` for Ansible; YAML well-formedness (plus `yamllint` only when the repo
pins a config); `bash -n`; `python -m py_compile`; JSON parse. `shellcheck`, `kubeconform` and `oxlint`
are absent on the host and their file types are skipped (not failed) until installed. On first run it
caught a real 160-char ansible-lint violation in freshly committed IaC, which was then fixed.

Wire the free, deterministic graders WatooM already has as a loop that runs **before** the owner sees a
change, and feeds failures back to the agent to fix:

| Artifact kind | Grader (read-only / dry-run) |
| --- | --- |
| Ansible roles / playbooks | `ansible-lint`, `ansible-playbook --syntax-check`, `--check` where safe |
| K8s manifests | `kubeconform` or `kubectl apply --dry-run=server` |
| Shell scripts | `shellcheck` |
| Fork TS/TSX | existing `oxlint` + `bun turbo typecheck` + package tests |
| Blender / runner locks | existing `fix.py check` + validation-suite receipt |

Properties:
- Graders are **harness-run; the verdict is the harness's, never the agent's self-report.** (The article's
  Darwin-Gödel-Machine warning: an agent that grades itself will fake logs and strip detector markers.)
- The loop is **bounded** (max iterations, wall-clock) and **non-mutating to production** — it only runs
  against the working tree / staging.
- This is the safest piece and can ship first; it changes no durable state.

### 3.2 Nightly memory pass — "sleep-time" curation (phase 3) — **IMPLEMENTED**

Delivered as `tools/watoom-code/self_learning/memory_curator.py` (tests alongside it) plus the IaC in
`ansible/roles/watoom-code/tasks/self_learning_curator.yml` (a bounded nightly `systemd` timer, wired into
`watoom-code-self-learning-controller.yml`, **off unless `watoom_learning_curator_enabled: true`**). It is
deterministic and uses no LLM/GPU. Design below; rollback/fix paths in §6.

A separate **GPU-idle** job curates memory. The agent **never edits its own memory**; a distinct curator
process does, the same separation the skill engine already enforces for skills.

Three memory kinds, kept **separately**:
- **Semantic** — facts (what is true). This is today's AgentMemory.
- **Episodic** — incidents (what happened: a problem, the context, the fix).
- **Procedural** — how-to rules (do-it-this-way), distilled from episodes.

Per-lesson bookkeeping (skillbook counters, as in agentic-context-engine / Hermes):
- `problem`, `fix`, `times_helped`, `last_validated`, `times_stale`.
- **Unused lessons are flagged for removal**, not silently kept.
- **Saved rules go stale**: a rule must be **re-validated before reuse** (a grader from 3.1, or an
  evaluator receipt), or it is demoted. No rule is trusted forever.

The nightly pass proposes additions/removals; **applying them to production memory stays behind the same
idle gate + operator approval** as skill revisions.

**Mining the sidecar's own accumulated incidents for a recurring pattern (added 2026-11-08):**
`memory_curator.pattern_lessons()` groups existing `episodic` lessons (today, the verification-loop incidents
already ingested by this same curator) by the grader/check name that failed, and once a grader has recurred
across at least `--pattern-min-occurrences` (default 3) DISTINCT files, writes ONE new `procedural` lesson
summarising the pattern — auto-applied to the sidecar immediately, exactly like every other source here (no
extra gate beyond the kill-switch and rollback already in place). Because it reads already-COMMITTED rows, a
freshly-ingested incident is only visible to the pattern check on the NEXT curator run, matching the real
15-minute timer's natural cadence. This is the "mine memory for lessons" capability, scoped to data this
curator already owns and has verified, rather than reaching into AgentMemory's own internal store (which this
module still never touches). Tests: `test_memory_curator.py`.

### 3.3 Learning from the owner's own fixes (phase 4) — **IMPLEMENTED**

Delivered in the same `memory_curator.py curate` pass. Below is the mechanism.

Two trace sources, turned into *procedural* rules by the nightly job:
1. **Owner hand-edits** — pair an agent-written file with the owner's later hand-edited commit (`git diff`
   of the owner's commits over agent-authored paths). The delta is the lesson.
2. **Session corrections** — explicit "no, do it this way" turns.

Each candidate rule carries its evidence (the diff / the quoted correction) and must pass a grader before
it can be proposed for promotion. **The agent proposes; the owner approves** (LangChain style). There is
**no unattended self-rewrite of the harness** — that directly conflicts with the Self-Harness failure mode
and with WatooM's standing owner-approved-promotion rule.

## 4. Non-negotiable safety invariants (carried from the engine + the article)

1. Graders live outside the agent's reach; verdicts come from the harness.
2. No durable change (skill, memory, rule, harness) activates without the idle gate **and** explicit owner
   approval. No automatic production deployment.
3. No unattended self-rewrite of the harness or of the agent's own memory.
4. Every saved skill/rule has usage counters and a staleness check; it is re-validated before reuse and
   flagged for removal when unused.
5. Raw conversations and command output never enter durable learning; only distilled lessons with evidence
   hashes do (today's engine already enforces this; the memory pass must too).
6. Skills/rules load as **name + one line, body on use** — already how native skills work; procedural
   rules follow the same shape.

## 5. Phased delivery (each phase is a separate owner-approved step)

- **Phase 1 — this document.** Owner review and sign-off on scope and invariants.
- **Phase 2 — verification loops.** Harness-run graders with feedback; no durable writes. Shippable alone.
- **Phase 3 — memory kinds + nightly curator.** Add episodic/procedural stores and counters; curator
  proposes, owner approves. Build on AgentMemory and `watoom_learning_status`.
- **Phase 4 — owner-fix learning.** Mine owner commits and corrections into procedural-rule proposals.

## 6. Decisions (owner delegated: "auto-improve, with a way to roll back or fix")

1. **Scope of "owner fixes":** homelab `main` only, rolling **30-day** window (`--since-days`, overridable).
   High-signal and bounded; the fork and game projects can be added later via `--repo`.
2. **Memory store:** a **sidecar** SQLite (`<watoom_learning_root>/lessons.sqlite`) the curator fully owns,
   keyed to AgentMemory IDs. It never mutates the live semantic memory, so it is independently resettable.
3. **Cadence:** **nightly auto-apply** of lessons (not per-proposal human approval — that is the
   "automatic"). Every write is one journalled transaction. Owner fixes ingest as `active` (the owner's own
   edits are trusted); verification incidents ingest as `pending` until re-seen. Lessons unused past 90 days
   are retired (flagged, never deleted).
4. **Grader / curator budget:** bounded nightly `systemd` timer on the homelab host — `CPUQuota=25%`,
   `MemoryMax=256M`, `RuntimeMaxSec=300`, `OnCalendar=03:30`. No LLM/GPU. (Heavier future graders can go to
   Bazzite.)
5. **Start point:** phase 2 shipped first on its own; phases 3–4 now follow as one curator.

### How to roll back or fix (three independent levers)

- **Off by default:** the timer is installed only when `watoom_learning_curator_enabled: true`. Set it back
  to false and re-apply the controller playbook to remove the unit entirely.
- **Runtime kill-switch:** `touch <watoom_learning_root>/curator-disabled` — the next `curate` is a no-op
  (`status: DISABLED`), no deploy needed.
- **Undo one night:** `memory_curator.py rollback --txn <id>` reverts exactly that transaction
  (every `curate` prints its `txn`).

What it never touches: code, the harness, the coordinator guard, or AgentMemory's own store. Those remain
owner-gated through the existing promotion path, by deliberate choice, even under "automatic".
