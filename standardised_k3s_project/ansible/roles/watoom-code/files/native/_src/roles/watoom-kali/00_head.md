---
description: General-purpose Kali execution, shell, files, interactive jobs and GUI through the verified workbench MCP.
mode: all
permissions:
  - action: "*"
    resource: "*"
    effect: allow
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

