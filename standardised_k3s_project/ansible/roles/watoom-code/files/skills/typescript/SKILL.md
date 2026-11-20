---
name: typescript
description: Use for TypeScript/JavaScript, Node, browser applications, Vite, npm dependency changes, typecheck/build errors, and frontend implementation.
---

# TypeScript / JavaScript

- Inspect `package.json`, lockfile, tsconfig, and existing scripts first.
- Use project-local npm dependencies; do not use `npm install -g`.
- Preserve strict compiler settings rather than suppressing errors.
- Do not delete required behavior only to satisfy unused-symbol checks.
- Prefer event wiring and actual usage when an unused function implements a required feature.
- Validate `typecheck` before `build` when both scripts exist.

## Temporary Vite validation

Do not run an unmanaged `npx vite ... &` through a bounded shell tool.

Preferred:

- Use the `web-smoke` skill and its Node child-process runner.
- Bind to `127.0.0.1`.
- Use strict/fixed port behavior.
- Require a real HTTP response.
- Always terminate the child process.
