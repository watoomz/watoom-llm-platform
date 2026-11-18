# Vite reference

Do not run an unmanaged `npx vite ... &` through a bounded shell tool.

Preferred:
- use the `web-smoke` skill and its Node child-process runner;
- bind to `127.0.0.1`;
- use strict/fixed port behavior;
- require a real HTTP response;
- always terminate the child process.
