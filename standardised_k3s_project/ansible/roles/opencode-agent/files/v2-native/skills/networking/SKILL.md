---
name: networking
description: Use for DNS, routing, sockets, VLAN-aware diagnosis, service reachability, packet-level evidence, and bounded network troubleshooting.
---

# Networking

- Establish scope and authorization before active probing.
- Prefer reachability/routing/DNS/socket evidence before broad scanning.
- Keep discovery bounded to the explicitly authorized target/range.
- Do not change router/VLAN/firewall state unless explicitly requested.
- Record command, target, and observed result; separate observation from inference.
- Avoid hardcoding topology into application code when configuration already exists.
