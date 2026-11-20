---
description: "Read-only external/internal research to answer a specific factual question (library behavior, API contract, competitive approach, documentation) using authoritative sources, feeding a decision rather than making one."
mode: subagent
steps: 240
permissions:
  - action: "*"
    resource: "*"
    effect: deny
  - action: "read"
    resource: "*"
    effect: allow
  - action: "wait"
    resource: "*"
    effect: allow
  - action: "sleep"
    resource: "*"
    effect: allow
  - action: "glob"
    resource: "*"
    effect: allow
  - action: "grep"
    resource: "*"
    effect: allow
  - action: "skill"
    resource: "*"
    effect: allow
  - action: "websearch"
    resource: "*"
    effect: allow
  - action: "webfetch"
    resource: "*"
    effect: allow
  - action: "question"
    resource: "*"
    effect: allow
  - action: "watoom_memory_recall"
    resource: "*"
    effect: allow
  - action: "watoom_memory_learn"
    resource: "*"
    effect: allow
  - action: "watoom_skill_search"
    resource: "*"
    effect: allow
  - action: "wlk_search"
    resource: "*"
    effect: allow
  - action: "wlk_symbol"
    resource: "*"
    effect: allow
  - action: "wlk_command"
    resource: "*"
    effect: allow
  - action: "wlk_get"
    resource: "*"
    effect: allow
  - action: "wlk_status"
    resource: "*"
    effect: allow
  - action: "wlk_feedback"
    resource: "*"
    effect: allow
  - action: "external_directory"
    resource: "*"
    effect: allow
  - action: "shell"
    resource: "*"
    effect: ask
  - action: "read"
    resource: "*.env.example"
    effect: allow
  - action: "subagent"
    resource: "watoom-critic"
    effect: allow
---

