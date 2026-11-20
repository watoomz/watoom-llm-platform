---
description: "Build and maintain CI/CD pipelines, test harnesses, build scripts and operational automation; writes pipeline/automation code, not application feature logic."
mode: all
steps: 480
permissions:
  - action: "*"
    resource: "*"
    effect: allow
  - action: "watoom-kali_*"
    resource: "*"
    effect: deny
  - action: "watoom_kali_*"
    resource: "*"
    effect: deny
  - action: "external_directory"
    resource: "/data/ai/*"
    effect: allow
  - action: "external_directory"
    resource: "/config/*"
    effect: allow
  - action: "external_directory"
    resource: "/home/opencode/.config/opencode/*"
    effect: allow
  - action: "write"
    resource: "/config/*"
    effect: deny
  - action: "edit"
    resource: "/config/*"
    effect: deny
  - action: "write"
    resource: "/home/opencode/.config/opencode/*"
    effect: deny
  - action: "edit"
    resource: "/home/opencode/.config/opencode/*"
    effect: deny
---

