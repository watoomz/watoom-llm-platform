# Native image tools

Image MCP tools are now exposed directly to the chat provider with their JSON schemas (`codemode: false`). This removes Code Mode wrapper syntax from the ordinary image workflow. Other MCP connectors retain their existing exposure. MCP authentication, permissions, coordinator/critic guards, GPU ownership and asynchronous verified result display are unchanged.

The live image skill names the native catalog/submission tools and their exact schemas. `settings.guidance` is nested; `guidance_scale` and top-level sampling fields are unsupported. Reuse catalog receipts, submit once with a stable request ID, then end the turn. Do not poll or replay an uncertain submission. Legacy JavaScript guidance is conditional on the actual catalog, rather than the normal path. Guard failures require the coordinator protocol, not repeated shell or MCP attempts.

Persisted in the application role's `opencode.json.j2`, idempotent image MCP migration and image prompting skill. Updated at verified native idle under the existing durable guard, then reloaded supported native locations. No application restart, AI execution or generation submission occurred.

Validation: eight feature-flag template combinations; idempotent migration preserving unrelated settings; five native MCP instruction tests; actual authenticated tools/list schemas passed through the installed native tool-definition renderer; live connector connected, new skill exposed and guard released. Source evidence: `/data/ai/helper-scripts/reports/image-native-tools-20261021`.
