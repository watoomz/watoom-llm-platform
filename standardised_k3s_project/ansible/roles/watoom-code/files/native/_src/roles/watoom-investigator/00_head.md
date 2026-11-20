---
description: "Read-only fact finding for a specific evidence gap: locate authoritative files/assets/APIs and report verified facts; not implementation, plan approval or final acceptance."
mode: subagent
steps: 360
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
