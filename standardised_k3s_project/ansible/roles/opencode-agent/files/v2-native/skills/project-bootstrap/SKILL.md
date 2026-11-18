---
name: project-bootstrap
description: Use when initializing a project, installing local dependencies, repairing package scripts, or establishing a reproducible project-local toolchain.
---

# Project bootstrap

- Inspect existing package manager/lockfile before changing anything.
- Install project dependencies locally.
- For Node prefer `npm install`, `npm install -D`, `npm create`, `npm exec`, or `npx`.
- Do not install project tools globally or into `/usr/local`.
- Do not use sudo.
- Add only dependencies required by the task.
- Establish repeatable validation scripts in the project rather than relying on one-off shell state.
