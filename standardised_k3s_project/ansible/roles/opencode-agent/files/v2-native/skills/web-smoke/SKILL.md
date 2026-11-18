---
name: web-smoke
description: Use when a local web app or Vite dev server must be started temporarily, validated over localhost, and cleaned up without unmanaged background processes.
---

# Web smoke test

Prefer a project-local runner that owns the temporary child process.

For Vite, use `scripts/smoke-vite.mjs` from this skill as the template:

- spawn project-local Vite;
- bind only to `127.0.0.1`;
- use `--strictPort`;
- wait for readiness with a bounded timeout;
- `fetch()` the root URL;
- require HTTP 200 and non-empty HTML;
- terminate the spawned child in `finally`;
- escalate to SIGKILL only for the owned child if graceful shutdown times out.

Do not use a bare `npx vite ... &` through a bounded shell tool.
