---
name: agentmemory-coordination
description: Context-efficient AgentMemory-first coordination for substantial OpenCode work using targeted recall, bounded serial work packages, frequent child checkpoints, resume-first recovery, progressive validation, persistent task state, and coordinator-reviewed durable memory.
---

# AgentMemory-First Coordination

## Purpose

Use this skill for substantial coordinated work.

The objective is to make long-running engineering work:

- context efficient
- incrementally verifiable
- easy to resume
- resistant to MAX STEPS/context exhaustion
- resistant to repeated investigation
- durable across compaction and new sessions
- safe when a child terminates part-way through a package

The operating principle is:

    current evidence provides truth
    AgentMemory retrieves durable history
    `.opencode/work` preserves task state
    package checkpoints preserve unfinished child work
    children perform bounded work
    validation determines progression
    coordinator keeps context lean

AgentMemory is important but never overrides current evidence.

---

# 1. Evidence precedence

Use this authority order:

1. current live/runtime evidence
2. current repository/source/configuration
3. current test and validation evidence
4. current package checkpoint state
5. `.opencode/work/**` project state
6. AgentMemory
7. assumptions

If memory or a checkpoint conflicts with current source/runtime evidence:

1. trust current evidence
2. determine whether stored state is stale
3. correct the active task state
4. stop relying on the stale fact
5. persist a corrected durable conclusion when useful

Never force current reality to match old memory.

---

## Mandatory AgentMemory invocation rule

For agent-driven recall, use the native OpenCode AgentMemory tool directly:

`agentmemory_memory_recall`

The installed AgentMemory plugin defines the underlying operation as
`memory_recall` and exposes AgentMemory tools with the
`agentmemory_memory_` prefix.

Do NOT invoke or discover AgentMemory through:

- Code Mode `execute`
- JavaScript `tools.agentmemory.*`
- generic `tools.search`
- generic `search`
- guessed `memory_search` operations
- guessed alternate AgentMemory names
- tool-inventory probing

Do not try multiple possible invocation mechanisms.

When targeted recall is appropriate:

1. invoke `agentmemory_memory_recall` directly using its declared tool schema;
2. inspect the returned result;
3. retain only facts relevant to the current package;
4. verify anything that could have changed against current source/runtime evidence.

If the native recall tool itself returns a real error:

1. record that exact error once;
2. do not fall back to Code Mode or generic search;
3. continue using `.opencode/work`, current source, runtime, and validation evidence.

`/recall` is the user-facing command workflow. Agents should use the native
AgentMemory recall tool for tool-driven retrieval.

The coordinator remains the owner of final durable memory writes. Never guess
a memory-write tool name; use only the exact native AgentMemory write tool
actually exposed by the runtime.

# 2. Targeted AgentMemory recall is the default

Before planning or delegating a non-trivial work package, determine whether previous
knowledge could materially:

- avoid rediscovery
- prevent a known regression
- restore architecture decisions
- recover validated baselines
- recover previous root causes
- recover important paths/constants
- restore context after compaction
- clarify what work already succeeded

If yes, perform targeted `/recall`.

Recall only material relevant to the current package.

Do not retrieve broad unrelated project history.

Examples:

## Implementation package

Recall:

- relevant architecture decisions
- behavioural contracts
- known compatible patterns
- exact important paths
- subsystem constraints

## Debugging package

Recall:

- earlier root causes
- previously attempted fixes
- confirmed good baselines
- known regressions
- failure signatures

## Validation package

Recall:

- acceptance criteria
- previously successful test method
- fragile behaviour
- expected result

## Infrastructure package

Recall:

- authoritative IaC paths
- deployment mechanism
- stable runtime constraints
- permissions/ownership conventions

Desired sequence:

    targeted recall
          ↓
    current task/package state
          ↓
    minimal current evidence
          ↓
    bounded action

---

# 3. Memory-first investigation

Before assigning investigation work, determine whether AgentMemory or project research
already contains the stable answer.

If it does:

- retrieve it
- verify only facts that could have changed
- avoid rediscovering stable information

Do not repeatedly spend context or tool calls rediscovering:

- stable paths
- validated architecture
- known configuration
- already-confirmed root causes
- established behavioural rules
- known engine/API findings
- already-proven limitations

If existing knowledge is incomplete, inspect only the missing evidence.

Persist a concise durable conclusion afterward when it is likely to matter again.

---

# 4. Aggressive package decomposition

Substantial work must be divided into small bounded packages.

A normal package should:

- answer one engineering question, OR
- implement one tightly coupled change
- normally touch approximately 1–4 files
- have explicit dependencies
- have explicit acceptance criteria
- have explicit validation
- define what is out of scope
- be independently resumable

Prefer:

    implement steering
    validate steering

over:

    implement the whole gameplay system

Prefer:

    establish one crash root cause

over:

    investigate all possible failures

If scope grows materially:

1. stop expanding the package
2. checkpoint completed state
3. record newly discovered dependencies
4. persist durable findings when appropriate
5. split remaining work into a new package

Never allow one child package to silently become an entire project.

---

# 5. Serial delegation

Use no more than one local child agent at a time.

Wait for that child to complete or terminate.

Review its state before dispatching another child.

The coordinator is primarily responsible for:

- decomposition
- dispatch
- dependency management
- evidence review
- acceptance decisions
- canonical task state
- durable AgentMemory
- recovery control

The child owns implementation/investigation details for its bounded package.

Do not use parallel child dispatch to increase throughput.

---

# 6. Package directory model

For substantial delegated packages use:

`.opencode/work/packages/<package-id>/`

Recommended contents:

    task.md
    progress.md
    research.md
    result.md

Not every package requires every file.

## task.md

Coordinator-owned package contract.

Contains:

    PACKAGE=
    ROLE=
    OBJECTIVE=
    DEPENDENCIES=
    FILES_OR_SYSTEMS_ALLOWED=
    ACCEPTANCE_CRITERIA=
    VALIDATION=
    OUT_OF_SCOPE=

The child should not silently broaden this contract.

## progress.md

Child-owned current recovery snapshot.

This is not a historical journal.

Keep it short and replace/update the current snapshot.

## research.md

Package-local evidence worth retaining during unfinished work.

Do not dump raw logs here.

## result.md

Final child handoff when the package reaches a terminal state.

---

# 7. Mandatory child checkpointing

A child performing substantial work must maintain durable package-local recovery state.

Do not wait until package completion.

The objective is:

> unexpected termination should lose only a small amount of useful work.

Checkpoint after meaningful state transitions such as:

- a meaningful implementation unit completes
- a significant investigation conclusion is established
- a successful validation completes
- implementation changes to validation
- a material defect/root cause is discovered
- a risky or potentially long-running operation is about to begin
- a risky or long-running operation completes
- several meaningful state-changing operations occurred since the last checkpoint
- the agent notices increasing context/step pressure
- immediately before returning control to the coordinator

Do not checkpoint every trivial edit or read.

As a practical default, if package state has materially advanced, avoid performing more
than roughly 3–5 meaningful state-changing operations without refreshing the checkpoint.

A checkpoint should be cheap.

---

# 8. Package checkpoint format

Keep `progress.md` concise and current.

Recommended format:

    PACKAGE=
    STATUS=PLANNED|IN_PROGRESS|IMPLEMENTED|VALIDATING|BLOCKED|PASS|FAIL
    LAST_CHECKPOINT=
    LAST_COMPLETED=

    FILES_CHANGED=
    - ...

    COMPLETED=
    - ...

    VALIDATED=
    - ...

    NOT_YET_VALIDATED=
    - ...

    CURRENT_FINDINGS=
    - ...

    NEXT_ACTION=

    KNOWN_ISSUES=
    - ...

    SAFE_TO_RESUME=yes|no

Important:

`IMPLEMENTED` does not mean `VALIDATED`.

Never mark work PASS merely because files were written.

---

# 9. Atomic checkpoint updates

Whenever practical, checkpoint writes should be atomic.

For shell-capable children, prefer:

    write progress.md.tmp
    validate that it is non-empty
    mv progress.md.tmp progress.md

If the editing tool already performs atomic file replacement, use that mechanism.

Do not deliberately leave a partially-written recovery file.

Do not build an endlessly appended checkpoint log.

The current snapshot is more useful for recovery than a giant transcript.

---

# 10. Resume-first child behavior

When starting or resuming an existing package, do not assume it begins from zero.

Read in this order:

1. package `task.md`
2. package `progress.md`
3. package `research.md` when relevant
4. package `result.md` if one exists
5. targeted AgentMemory
6. current source/configuration
7. current runtime/test evidence

Then reconcile stored state against current reality.

If a previous child wrote code but did not validate it:

- preserve the implementation
- validate it
- fix only what evidence shows is wrong

Do not rewrite completed work merely because the previous child terminated.

Continue from `NEXT_ACTION` unless current evidence invalidates it.

---

# 11. Same-package recovery after termination

A child termination caused by:

- MAX STEPS
- context limit
- compaction
- tool/runtime interruption
- process failure

does not automatically invalidate the package.

The coordinator should:

1. inspect package `progress.md`
2. inspect current source
3. inspect available validation
4. determine actual state
5. dispatch a replacement child using the SAME package ID when appropriate
6. explicitly instruct it to RESUME rather than restart

Only restart from zero if evidence shows existing work is unusable.

---

# 12. Coordinator owns canonical state

The coordinator owns canonical project-level:

    .opencode/work/task.md
    .opencode/work/progress.md
    .opencode/work/research.md
    .opencode/work/decisions.md

Package checkpoints are recovery state.

Global progress is accepted project state.

After a child finishes or terminates:

1. inspect package checkpoint
2. inspect current source/runtime
3. review validation evidence
4. decide actual package status
5. update canonical global progress
6. persist verified durable AgentMemory
7. resume, repair, or advance

Do not promote an unfinished child checkpoint directly to canonical PASS.

---

# 13. Coordinator owns durable `/remember`

Children may use `/recall`.

Children should not independently fill AgentMemory with intermediate work.

Children return concise memory candidates.

The coordinator performs final `/remember` decisions after verification.

Suggested child field:

    MEMORY_CANDIDATES=
    - ...
    - ...

Before remembering a candidate, verify against:

- current source
- current runtime
- current tests
- package evidence

This prevents:

- speculative memory
- stale memory
- contradictory memory
- duplicate memory
- superseded failures becoming durable history

---

# 14. What belongs in AgentMemory

Good durable candidates include:

- architecture decisions
- authoritative important paths
- stable behavioural contracts
- important constants/configuration
- confirmed root causes
- confirmed fixes
- meaningful validation methods
- meaningful validation results
- durable environment constraints
- compatibility findings
- known long-lived risks/dependencies

Store conclusions, not raw evidence.

Good example:

    Edge turnaround owns heading while active; normal steering resumes only after the
    turnaround state exits.

Bad example:

    400 lines of frame-by-frame test output.

---

# 15. What does not belong in AgentMemory

Do not persist:

- raw logs
- large command output
- temporary build output
- speculative theories
- disproven hypotheses
- failures superseded by a successful fix
- whole source files
- whole diffs
- detailed chain-of-thought/reasoning
- transient data useful only for the next command
- duplicate versions of an already-stored fact

---

# 16. `.opencode/work` versus AgentMemory

Use `.opencode/work/**` for active task state:

- objective
- active milestone
- active package
- queue
- progress
- package recovery
- research
- decisions
- blockers
- acceptance state

Use AgentMemory for knowledge likely to help:

- future packages
- later sessions
- related future work
- regression prevention
- compaction recovery

Neither overrides current source/runtime evidence.

---

# 17. Context-efficient default loop

For substantial work:

    targeted /recall
          ↓
    inspect global work state
          ↓
    inspect package checkpoint if resuming
          ↓
    inspect only necessary current evidence
          ↓
    define one bounded package
          ↓
    delegate one child
          ↓
    child checkpoints while working
          ↓
    child implements/investigates
          ↓
    child runs targeted validation
          ↓
    child refreshes checkpoint/result
          ↓
    coordinator reviews concise handoff
          ↓
    coordinator verifies acceptance
          ↓
    update canonical `.opencode/work`
          ↓
    coordinator persists durable memory
          ↓
    discard unnecessary active context
          ↓
    select next package

---

# 18. Read-budget discipline

Avoid expensive context use.

Prefer:

- exact grep/search
- targeted line ranges
- known symbol lookup
- narrow configuration queries
- existing research summaries
- package checkpoint review

Avoid:

- repeatedly reading entire large files
- repeatedly listing huge directory trees
- rereading the same source without a reason
- reloading broad AgentMemory
- copying giant command output into prompts

Before rereading large material ask:

> What exact unanswered question requires this read?

If there is no specific unanswered question, do not reread it.

---

# 19. Evidence caching

Stable investigation results should be reused.

Use package/project research files for evidence that later packages may need.

Examples:

- exact source location of a behaviour
- authoritative API signature
- validated deployment path
- known file ownership constraint
- stable test command
- confirmed model/runtime setting

Do not rerun expensive searches merely to reproduce already-established stable facts.

Revalidate only when the fact could reasonably have changed.

---

# 20. Validation ladder

Use the cheapest meaningful validation first.

Typical progression:

1. syntax/parser/static check
2. targeted unit or narrow behavioral test
3. subsystem integration test
4. broader project smoke test
5. expensive end-to-end validation

Do not run the most expensive validation after every trivial edit.

However, before package PASS, run whatever level is required by its acceptance criteria.

If a cheap validation fails:

- fix that failure first
- do not waste time on downstream expensive validation

---

# 21. Mutation discipline

Keep each package's mutation surface small.

Before editing:

- know which files are in scope
- know what behavior is being changed
- know how it will be validated

Avoid opportunistic cleanup.

Do not refactor unrelated code merely because it was noticed.

Record unrelated findings for later packaging.

This reduces:

- regression risk
- diff size
- review cost
- context cost
- recovery complexity

---

# 22. Log discipline

Large logs should not live in active coordinator context.

When logs are needed:

- save full logs to an appropriate artifact/log path
- extract the relevant lines
- summarize the conclusion
- record the path if future investigation may need the full log

Do not repeatedly paste full build/runtime logs into child prompts or AgentMemory.

---

# 23. Child task contract

Every substantial child task should receive:

    ROLE
    PACKAGE_ID
    OBJECTIVE
    RELEVANT MEMORY TO RECALL
    CURRENT STATE / DEPENDENCIES
    PACKAGE_CHECKPOINT_PATH
    FILES OR SYSTEMS ALLOWED TO TOUCH
    ACCEPTANCE CRITERIA
    VALIDATION
    OUT OF SCOPE
    REQUIRED RESULT FORMAT

The child should receive only context needed for its package.

Suggested result:

    RESULT=
    PACKAGE=
    CHECKPOINT_PATH=
    LAST_CHECKPOINT=
    FILES_CHANGED=
    IMPLEMENTED_OR_FOUND=
    VALIDATION_RUN=
    VALIDATION_RESULT=
    DEFECTS_FOUND=
    DEFECTS_FIXED=
    REMAINING=
    NEXT_ACTION=
    SAFE_TO_RESUME=
    MEMORY_CANDIDATES=

---

# 24. Handoff under step/context pressure

If a child detects that it may not finish before step/context exhaustion:

1. stop starting new optional work
2. complete the current safe operation if practical
3. refresh `progress.md`
4. record exact `NEXT_ACTION`
5. distinguish validated from unvalidated work
6. make `SAFE_TO_RESUME` accurate
7. preserve useful research
8. return a concise handoff if still able

Do not spend remaining budget writing a long narrative.

Recovery state is more valuable.

---

# 25. Coordinator recovery behavior

If a child disappears without a normal result:

1. do not assume failure
2. inspect package checkpoint
3. inspect changed files
4. inspect recent validation artifacts
5. reconstruct the smallest missing state
6. resume the same package where possible

The replacement child prompt should state explicitly:

    MODE=RESUME
    PACKAGE_ID=<same package>
    START_FROM=<checkpoint NEXT_ACTION>

Do not cause repeated work merely because the previous child did not get to its final
message.

---

# 26. Context compaction and session recovery

The project must remain resumable after coordinator compaction or a new session.

A fresh coordinator should reconstruct state primarily from:

    targeted AgentMemory
        +
    `.opencode/work/**`
        +
    package checkpoints
        +
    current repository/source
        +
    current runtime/test evidence

Important state must not exist only in conversational context.

Before a likely context boundary or after a major milestone:

1. make canonical global work state current
2. ensure active child package is checkpointed
3. persist verified durable AgentMemory
4. record the next bounded package
5. record blockers
6. discard irrelevant historical detail

---

# 27. Global work-state files

Recommended:

    .opencode/work/task.md
    .opencode/work/progress.md
    .opencode/work/research.md
    .opencode/work/decisions.md
    .opencode/work/packages/

## Global task.md

Keep focused on:

- current milestone
- current/next package
- project-level completion gate
- major dependencies

## Global progress.md

Canonical accepted status only.

Use concise entries such as:

    PACKAGE=
    STATUS=
    ACCEPTED_VALIDATION=
    FILES_CHANGED=
    RESULT=
    NEXT=

Do not turn it into a raw chronological transcript.

## research.md

Reusable project evidence.

## decisions.md

Durable task/project architecture decisions with concise rationale.

---

# 28. Acceptance before progression

A child saying "done" is not sufficient.

Before advancing:

1. inspect child result/checkpoint
2. verify required evidence exists
3. run or inspect required validation
4. confirm acceptance criteria
5. update canonical global progress
6. persist durable memory
7. select next package

If validation fails, create or resume a small repair package.

Do not stack unrelated implementation on top of a broken package.

---

# 29. Failure handling

Normal implementation failures should remain local.

For:

- parser errors
- compile errors
- failed tests
- invalid paths
- bad configuration
- runtime regressions
- mistaken assumptions

create or resume a bounded repair package.

If failure reveals a bad architectural assumption:

1. capture evidence
2. correct task decision
3. correct stale memory
4. define smallest remediation package
5. revalidate

Do not restart the whole project unless evidence proves it necessary.

---

# 30. Automatic progression

After a package passes:

1. update global work state
2. persist useful durable memory
3. identify next dependency-ready package
4. retrieve only relevant memory
5. create/update its package contract
6. delegate one child
7. continue

Do not require the user to manually coordinate routine progression already inside the
approved task scope.

Stop only for:

- genuine external blockers
- destructive actions requiring approval
- material scope changes
- decisions that cannot safely be inferred
- explicit user-requested checkpoints

---

# 31. Efficiency heuristics

Use these defaults:

## Prefer reuse over rediscovery

If a stable result already exists, reuse it.

## Prefer summaries over transcripts

Store actionable conclusions.

## Prefer narrow child context

Do not pass complete project history.

## Prefer one subsystem per package

Smaller diffs are easier to validate and resume.

## Prefer early cheap failure detection

Parser/unit checks before expensive integration.

## Prefer repair over restart

Resume valid partial work.

## Prefer exact searches over directory-wide scans

Reduce I/O and context.

## Prefer durable state over conversational memory

Anything important for recovery must be written down.

## Prefer current snapshots over append-only progress logs

Recovery should answer "where are we now?"

---

# 32. Completion

A substantial task is complete only when its explicit completion gate is satisfied.

Implementation completion is not validation completion.

Final coordinator report should summarize:

- packages completed
- final validation
- durable decisions
- known differences
- remaining defects
- blockers
- recommended next step

Do not include giant logs.

---

# 33. Core operating model

Use this by default for substantial coordinated work:

    remember durable history
           ↓
    recall only what is needed
           ↓
    package work narrowly
           ↓
    checkpoint while working
           ↓
    resume instead of redo
           ↓
    validate progressively
           ↓
    promote only verified state
           ↓
    keep coordinator context lean
