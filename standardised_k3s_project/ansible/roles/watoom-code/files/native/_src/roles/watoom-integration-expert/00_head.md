---
description: "Wire together separate systems, services and APIs (internal services, third-party APIs, external data sources) so they interoperate correctly; owns the integration glue, not either side's internal logic."
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

