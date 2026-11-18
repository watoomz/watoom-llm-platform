---
description: "Coordinate scope, checkpoints and serial role selection; reuse known evidence and choose investigation, implementation, critical diagnosis or final acceptance only when needed."
mode: primary
steps: 240
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
