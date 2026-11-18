---
title: API, SDK & platform reference
nav: LLM API & reference
summary: The reference hub for the local AI platform — native application, inference router, privileged controller, Model Manager and Toolkit contracts, plus downloadable schemas, a source map and runnable clients.
---

## Choose the right interface

| Goal | Interface | Authentication and boundary |
|---|---|---|
| Sessions, projects, inboxes, agents and permissions | WatooM Code `/api/*`, port 4096 | Native Basic/session authentication and application permissions |
| Text/vision inference and model discovery | `llm-router`, port 8000 | Approved internal access; no independent API-key enforcement in current Python router |
| GPU ownership/leases/recovery | Controller UNIX sockets | Privileged operator/worker peers; not an app/browser API |
| Model metadata/install/generate/remove | Model Manager `/model-manager/api/*` | Manager login/Basic plus same-origin CSRF on mutation |
| Bounded engine jobs | Toolkit `/api/*`, port 8879 | Toolkit bearer token and validated task contract |
| MCP capabilities | Installed native registrations | Actual discovered tool schema and agent permissions |

A session prompt is not a chat-completion request. The router does not create native sessions or authorize project writes. A generic OpenAI-compatible client cannot use the native `/api/session` contract without a separate adapter.

## Downloadable reference artifacts

- [Upstream native schema MIT notice](/guide/assets/llm-platform/OPENCODE-LICENSE.txt)
- [Pinned native OpenAPI JSON](/guide/assets/llm-platform/watoom-code.openapi.json)
- [Maintained router OpenAPI JSON](/guide/assets/llm-platform/router.openapi.json)
- [Python native reference client](/guide/assets/llm-platform/watoom_client.py)
- [Node fetch reference client](/guide/assets/llm-platform/watoom_client.mjs)
- [Version and source verification](/guide/assets/llm-platform/verification.json)

The native snapshot is copied byte-for-byte from `packages/protocol/openapi.json` in production application commit `786682b1489e92cba4e4b5a277bd49c565c94e4f`. It describes the selected experimental HttpApi surface, not every dynamically maintained operator extension. Its empty operation `security` arrays do not disable deployed authentication middleware. Configure authentication explicitly in generated clients. The router contract covers owned routes and qualified inference entry points, not every llama-server endpoint.

Reference clients are small examples, not a separately versioned official SDK or a promise of cross-version compatibility. The Python client uses only the standard library; the JavaScript example targets Node with `fetch`, `Buffer` and `AbortSignal.timeout`. They contain no hidden POST retries. Schema/runtime tests and actual native acceptance remain necessary before production automation.

## Native authentication and errors

Normal operator requests use `Authorization: Basic BASE64(opencode:password)` over the approved HTTPS endpoint. Browser sign-in uses native session authentication; same-origin cookie policy applies. Never put passwords in URLs, source, browser storage snippets or shell history. Runtime secrets come from approved private configuration. Do not disable TLS verification for examples.

The source includes ticketed connection exceptions for specific PTY/pairing handlers; those handlers validate their tickets. They are not a general authentication bypass. Browser assets can be public so the sign-in page loads before authentication.

Native results commonly wrap resources in `data`; not all endpoints use identical wrappers. Errors can carry `_tag` and `message`. Inspect the pinned operation schema instead of hard-coding a universal envelope. Common statuses: 400 invalid input, 401 unauthorized, 404 missing session/resource and 409 conflict. An unavailable transport is not a completed or rejected mutation: reconcile existing IDs/state before retrying.

Read-only example; `curl` prompts for the password rather than embedding it:

```bash
export WATOOM_BASE_URL=https://watoom-code.internal.homelab.example
curl --fail-with-body --user opencode "$WATOOM_BASE_URL/api/info"
curl --fail-with-body --user opencode "$WATOOM_BASE_URL/api/session?limit=20&order=desc"
```

## Native session lifecycle

`POST /api/session` creates a session and returns `data` containing a `Session.Info` resource. Location is an object with a `directory`; model is an object with `providerID` and `id`, not a router URL. Required resource fields include identity, project, cost, token usage, timestamps and location. Optional agent/title/model fields depend on the operation.

Example body for an explicitly authorized project/session creation:

```json
{
  "title": "Review a scoped change",
  "agent": "watoom-workflow",
  "model": {"providerID": "watoom", "id": "swift-qwen38-coder"},
  "location": {"directory": "/data/ai/projects/homelab/homelab-llm"}
}
```

`POST /api/session/{sessionID}/prompt` durably admits input. The required field is `text`; optional fields include `id`, attachments, metadata, delivery and `resume`. The response is `data: Session.Inbox.User`, not an assistant answer. Use a stable caller-managed message ID where appropriate; after an ambiguous result inspect existing inbox/messages before resubmitting. This is not a claim that arbitrary request IDs make all endpoints idempotent.

```json
{"id":"msg_example_stable_identifier","text":"Inspect the requested files and report findings.","resume":true}
```

Use `GET /api/session/{sessionID}/message`, the active-session endpoint and native events to observe progress. List pagination returns `cursor.previous`/`cursor.next`; cursors are opaque, may be null, and must be reused with the endpoint's documented query semantics. Do not synthesize cursor values or delete an inbox item just to clear a blocked state.

Changing an agent/model/location, interrupting, compacting, reverting or replying to a permission/form is a mutation. A new model selection affects submitted work through native semantics; it does not authorize direct deployment changes.

## Python and Node reference use

Provision credentials in the process environment through the existing private mechanism, not a committed `.env` file. Running the Python example as a script calls only `/api/info` and prints version/reachability. Importing it performs no network call.

```python
from watoom_client import NativeClient
import os

client = NativeClient(os.environ["WATOOM_BASE_URL"], os.environ["WATOOM_PASSWORD"])
print(client.info().get("version"))
page = client.sessions(limit=20)
# Use page["cursor"]["next"] for a later page when present.
# Only after user authorization:
# session = client.create_session(directory, title)
# admitted = client.prompt(session["data"]["id"], text, message_id=stable_id)
```

```javascript
import { NativeClient } from "./watoom_client.mjs";
const client = new NativeClient(process.env.WATOOM_BASE_URL, process.env.WATOOM_PASSWORD);
const info = await client.info();
console.log(info.version);
```

The examples deliberately expose mutations as explicit method calls. They neither auto-create a session nor continue execution after an uncertain transport outcome. Do not print authorization headers or full private responses in logs. For generated clients, pin the supplied schema hash/version and test your integration against the matching deployed source.

## Native event stream

`GET /api/event` returns `text/event-stream`. Its contract is volatile: a slow consumer can overflow/fail and events during disconnection can be missed. Frames include event/id/data and can carry `effect/httpapi/stream/failure`. The stream is not a durable replay log.

Parse SSE frames rather than assuming one HTTP chunk equals one event. Preserve UTF-8 boundaries and accumulate multiline `data:` fields. On reconnect, refetch durable session/message/inbox/job state and reconcile. Do not repeat a prompt merely because its completion event was missed. Native event framing differs from inference SSE, which uses OpenAI-style `data:` deltas and a `[DONE]` terminator.

## Inference router

The source is `ansible/roles/llm-model-lab/files/gpu-controller-router.py`. Normal base includes `/v1` for completion clients. Health/lifecycle paths are at the service root.

| Method/path | Meaning | Mutation |
|---|---|---|
| `GET /health` or `/` | Process health and active deployment | No explicit switch |
| `GET /v1/models` | OpenAI-compatible model listing | Discovery only |
| `GET /models` | Lifecycle catalog | Discovery only |
| `GET /models/status` | Lifecycle status | No explicit switch |
| `POST /models/load` | Request a controller-mediated model load | Yes |
| `POST /v1/chat/completions` | Chat, tools and image content when backend supports it | Inference; explicit model can request eligible switch |
| `POST /v1/completions` | Completion interface | Inference |

Unknown `/models/load` model returns 404 with requested/mapped/catalog information. A busy/unavailable/refused load returns 503. `active-model` asks for the active backend and returns a structured no-active-model 503 when none is available. Explicit aliases resolve to the backend canonical model ID; the router preserves caller tool schemas/tool choice rather than maintaining a second tool allowlist.

```bash
export ROUTER_BASE=http://llm-router.llama-cpp.svc.cluster.local:8000
curl --fail-with-body "$ROUTER_BASE/v1/models"
curl --fail-with-body -H 'Content-Type: application/json' \
  "$ROUTER_BASE/v1/chat/completions" \
  --data '{"model":"swift-qwen38-coder","messages":[{"role":"user","content":"Reply with ready."}],"max_tokens":64,"temperature":0,"stream":false}'
```

Run these only from an approved reachable network and authorized workload. Internal HTTP is not an invitation to expose the service publicly. Backend-native `/slots`, `/props`, `/tokenize` and `/detokenize` are operator/backend interfaces, not portable application SDK methods.

### Streaming, tools and vision

For `stream:true`, role-only chunks may arrive before generated content. TTFT should distinguish first generated content/tool data from a role header. Assemble tool fragments by index, then concatenate ID/name/argument fragments before JSON validation. Wait for valid complete arguments and runtime authorization before executing a tool. Associate each tool result with its exact `tool_call_id` and send it in the continuation. Never execute model-supplied arbitrary text as a shell command.

Reasoning fields and chat-template options are backend/version-specific. A continuation may intentionally strip reasoning while preserving assistant/tool history. Reordering tools or changing a stable prefix can invalidate cache reuse. Image requests use supported multimodal message content and the verified model/projector; a listed model is not automatically vision-qualified.

No universal “safe POST retry” exists for streaming generation or model switching. After a disconnect, reconcile controller/request accounting and native job state. Controller refusal must not trigger direct scaling.

## Privileged controller SDK

Maintained Python client: `tools/llm/watoom-gpu-controller/client.py`. `GPUClient(socket_path, timeout=10).call(action, **fields)` sends one newline-delimited JSON request, validates the bounded response and raises `ControllerUnavailable` or `ControllerRejected`. There is no fallback to `kubectl`.

Operator-only read example:

```python
from client import GPUClient
# Use the router_socket read from the reviewed controller config, not a guessed path.
status = GPUClient(config["router_socket"]).call("status")
assert status["uncertain"] is False
```

Router endpoint actions are scoped to status/eligibility/model request and inference lease accounting. Private worker actions include begin, activate, asset-saved, restore, validated recovery and lifecycle enrollment/retirement. Exact action fields and peer/process/generation checks are in `g3h_service.py`, `inference_leases.py` and `model_lifecycle.py`.

`MeshWorkerAdapter.begin(job_id)` returns a generation; `activate(job_id,generation)` and `restore(job_id,generation)` use that exact identity. Uncertain activate/restore transport outcomes must not be retried under a new ID. Root peer access alone is not the complete authorization contract. The offline `gateway.py` is a simulator, not the production daemon.

## Model Manager API

Base prefix is `/model-manager`. GETs require manager authentication except login; mutations require authentication, exact configured `Origin`, and `X-CSRF-Token` obtained from `GET /api/session`. Credentials differ from the native application's. Login sets an HTTP-only, SameSite cookie with Secure on HTTPS. Never put credentials in a browser URL or source file.

| Endpoint under prefix | Purpose/result |
|---|---|
| `GET /api/session` | CSRF token for current manager process |
| `GET /api/models`, `/api/jobs`, `/api/result?id=...` | Catalog, queued/running jobs and result state |
| `POST /api/inspect` | `{url}` returns inspected immutable metadata and proposed settings |
| `POST /api/install` | Exact URL/revision/variant/settings; compatible base when required; returns 202 job |
| `POST /api/generate` | Installed id/revision/prompt; returns 202 job |
| `POST /api/cancel`, `/api/retry` | Existing job identity, explicit lifecycle request |
| `POST /api/remove-plan` | Fresh identity-scoped removal confirmation |
| `POST /api/remove` | Matching confirmation and delete choice; returns 202 job |
| `POST /api/overrides` | Persist validated overrides or safe reset |
| `POST /mcp` | Narrow installed-image MCP adapter with separate token/scope |

Invalid schema/selection is 400; unauthorized 401; Origin/CSRF rejection 403; absent route 404; maintenance/unavailable operation 503. Exact install payload includes the current metadata selection; do not invent variant IDs or skip inspect. Downloaded/configured/registered/tested are separate statuses. Raw metadata is never executable code. The manager browser/API is not a generic Hugging Face SDK.

## Toolkit and MCP integration

Toolkit source is `tools/watoom-toolkit/agent.py`. `/healthz` is a public health probe. Other API calls require `Authorization: Bearer <Toolkit token>`; the process refuses to bind without a sufficiently long configured token. POST bodies must be JSON objects of 1–4096 bytes.

| Route | Contract |
|---|---|
| `GET /api/catalog` | Profiles, installed packs, generators and declared capabilities |
| `GET /api/jobs` | Recent persisted job receipts |
| `POST /api/jobs` | Validated task contract, e.g. `{ "task": "probe" }` for discovery |
| `POST /api/jobs/cancel` | Existing job cancellation contract |
| `GET/POST /api/maintenance` | Scoped job-admission status/change; operator workflow |
| `POST /api/profile-requests` | Validated profile set; 202 `AWAITING_HOST_APPROVAL`, not live package installation |

Task-specific engine/asset payloads are maintained in the owning schemas, not inferred from this table. Use installed MCP discovery to inspect Mesh, memory, image and tool interfaces. Availability of a native skill does not add tools or permissions. Stable request IDs, validated input hashes and durable receipts are required where the worker contract declares them.

## Compatibility and validation

Pin schema/source/image versions together. Test at least authentication rejection, native response wrappers, admission versus completion, pagination/reconnect, SSE fragmentation, tool argument assembly/result IDs, selected model behavior and controller refusal. Reference-client tests use a fake transport and create no real sessions. Live documentation verification uses read-only HTTP; it does not run a model switch or generation.

The pinned native schema contains 113 paths and 136 operations. The following catalog lists every operation in the pinned native schema. It does not imply all are permitted for every role, installed integration or project. Experimental routes and administrative mutations require additional review. Operator deployment-guard extensions are implementation-specific and intentionally not presented as ordinary SDK calls.

## Native endpoint catalog

| Method | Path | Operation | Summary |
|---|---|---|---|
| GET | `/api/info` | `server.info` | Get server info |
| GET | `/api/location` | `location.get` | Get location |
| POST | `/api/location/reload` | `location.reload` | Reload configuration |
| GET | `/api/agent` | `agent.list` | List agents |
| GET | `/api/agent/{agentID}` | `agent.get` | Get agent |
| GET | `/api/plugin` | `plugin.list` | List plugins |
| POST | `/api/plugin/check` | `plugin.check` | Check plugin updates |
| POST | `/api/plugin/update` | `plugin.update` | Update plugins |
| GET | `/api/session` | `session.list` | List sessions |
| POST | `/api/session` | `session.create` | Create session |
| GET | `/api/experimental/session/stats` | `experimental.session.stats` | Get session statistics |
| POST | `/api/experimental/session/import` | `experimental.session.import` | Import session |
| GET | `/api/experimental/session/{sessionID}/export` | `experimental.session.export` | Export session |
| GET | `/api/session/active` | `session.active` | List active sessions |
| GET | `/api/session/{sessionID}` | `session.get` | Get session |
| DELETE | `/api/session/{sessionID}` | `session.remove` | Delete session |
| PATCH | `/api/session/{sessionID}` | `session.update` | Update session |
| POST | `/api/session/{sessionID}/fork` | `session.fork` | Fork session |
| POST | `/api/session/{sessionID}/agent` | `session.switchAgent` | Switch session agent |
| POST | `/api/session/{sessionID}/model` | `session.switchModel` | Switch session model |
| POST | `/api/session/{sessionID}/move` | `session.move` | Move session |
| POST | `/api/session/{sessionID}/prompt` | `session.prompt` | Send message |
| POST | `/api/session/{sessionID}/command` | `session.command` | Run command |
| POST | `/api/experimental/session/{sessionID}/skill` | `experimental.session.skill` | Activate skill |
| POST | `/api/session/{sessionID}/synthetic` | `session.synthetic` | Add synthetic message |
| POST | `/api/session/{sessionID}/shell` | `session.shell` | Run shell command |
| POST | `/api/session/{sessionID}/compact` | `session.compact` | Compact session |
| POST | `/api/experimental/session/{sessionID}/wait` | `experimental.session.wait` | Wait for session |
| POST | `/api/session/{sessionID}/revert/stage` | `session.revert.stage` | Stage session revert |
| DELETE | `/api/session/{sessionID}/revert` | `session.revert.clear` | Clear staged revert |
| POST | `/api/session/{sessionID}/revert/commit` | `session.revert.commit` | Commit staged revert |
| GET | `/api/session/{sessionID}/context` | `session.context` | Get session context |
| GET | `/api/session/{sessionID}/diff` | `session.diff` | Diff session turns |
| GET | `/api/session/{sessionID}/inbox` | `session.inbox.list` | List session inbox |
| DELETE | `/api/session/{sessionID}/inbox/{inboxID}` | `session.inbox.cancel` | Cancel inbox input |
| PATCH | `/api/session/{sessionID}/inbox/{inboxID}` | `session.inbox.update` | Update inbox item |
| GET | `/api/experimental/session/{sessionID}/instructions/entries` | `experimental.session.instructions.entry.list` | List instruction entries |
| PUT | `/api/experimental/session/{sessionID}/instructions/entries/{key}` | `experimental.session.instructions.entry.put` | Put instruction entry |
| DELETE | `/api/experimental/session/{sessionID}/instructions/entries/{key}` | `experimental.session.instructions.entry.remove` | Remove instruction entry |
| POST | `/api/session/{sessionID}/generate` | `session.generate` | Generate text from session context |
| GET | `/api/experimental/session/{sessionID}/log` | `session.log` | Read the session log |
| POST | `/api/session/{sessionID}/interrupt` | `session.interrupt` | Interrupt session execution |
| POST | `/api/session/{sessionID}/background` | `session.background` | Background blocking session tools |
| GET | `/api/session/{sessionID}/message/{messageID}` | `session.message.get` | Get session message |
| GET | `/api/session/{sessionID}/form` | `session.form.list` | List session forms |
| POST | `/api/session/{sessionID}/form` | `session.form.create` | Create session form |
| GET | `/api/session/{sessionID}/form/{formID}` | `session.form.get` | Get session form |
| DELETE | `/api/session/{sessionID}/form/{formID}` | `session.form.cancel` | Cancel form |
| POST | `/api/session/{sessionID}/form/{formID}/reply` | `session.form.reply` | Reply to form |
| PUT | `/api/session/{sessionID}/environment` | `session.environment` | Set session environment |
| POST | `/api/session/{sessionID}/view` | `session.view` | View session |
| GET | `/api/session/{sessionID}/message` | `session.message.list` | Get session messages |
| GET | `/api/model` | `model.list` | List models |
| GET | `/api/model/default` | `model.default` | Get default model |
| POST | `/api/experimental/generate` | `experimental.generate.text` | Generate text |
| GET | `/api/provider` | `provider.list` | List providers |
| GET | `/api/provider/{providerID}` | `provider.get` | Get provider |
| GET | `/api/integration` | `integration.list` | List integrations |
| GET | `/api/integration/{integrationID}` | `integration.get` | Get integration |
| POST | `/api/experimental/integration/wellknown` | `experimental.integration.wellknown.add` | Add wellknown integration |
| POST | `/api/integration/{integrationID}/connect/key` | `integration.connect.key` | Connect with key |
| POST | `/api/integration/{integrationID}/connect/oauth` | `integration.oauth.connect` | Begin OAuth connection |
| GET | `/api/integration/{integrationID}/connect/oauth/{attemptID}` | `integration.oauth.status` | Get OAuth attempt status |
| DELETE | `/api/integration/{integrationID}/connect/oauth/{attemptID}` | `integration.oauth.cancel` | Cancel OAuth connection |
| POST | `/api/integration/{integrationID}/connect/oauth/{attemptID}/complete` | `integration.oauth.complete` | Complete OAuth connection |
| POST | `/api/integration/{integrationID}/connect/command` | `integration.command.connect` | Begin command connection |
| GET | `/api/integration/{integrationID}/connect/command/{attemptID}` | `integration.command.status` | Get command attempt status |
| DELETE | `/api/integration/{integrationID}/connect/command/{attemptID}` | `integration.command.cancel` | Cancel command connection |
| GET | `/api/mcp` | `mcp.list` | List MCP servers |
| PUT | `/api/experimental/mcp/{server}` | `experimental.mcp.add` | Add MCP server |
| DELETE | `/api/experimental/mcp/{server}` | `experimental.mcp.remove` | Remove MCP server |
| POST | `/api/experimental/mcp/{server}/connect` | `experimental.mcp.connect` | Connect MCP server |
| POST | `/api/experimental/mcp/{server}/disconnect` | `experimental.mcp.disconnect` | Disconnect MCP server |
| GET | `/api/mcp/resource` | `mcp.resource.catalog` | List MCP resources |
| PATCH | `/api/credential/{credentialID}` | `credential.update` | Update credential |
| DELETE | `/api/credential/{credentialID}` | `credential.remove` | Remove credential |
| POST | `/api/credential/{credentialID}/activate` | `credential.activate` | Activate credential |
| GET | `/api/project` | `project.list` | List projects |
| PATCH | `/api/project/{projectID}` | `project.update` | Update project |
| GET | `/api/form` | `form.list` | List pending forms |
| GET | `/api/permission/request` | `permission.request.list` | List pending permission requests |
| GET | `/api/permission/saved` | `permission.saved.list` | List saved permissions |
| DELETE | `/api/permission/saved/{id}` | `permission.saved.remove` | Remove saved permission |
| POST | `/api/session/{sessionID}/permission` | `session.permission.create` | Create permission request |
| GET | `/api/session/{sessionID}/permission` | `session.permission.list` | List session permission requests |
| GET | `/api/session/{sessionID}/permission/{requestID}` | `session.permission.get` | Get permission request |
| POST | `/api/session/{sessionID}/permission/{requestID}/reply` | `session.permission.reply` | Reply to pending permission request |
| GET | `/api/fs/read/*` | `fs.read` | Read file |
| GET | `/api/fs/list` | `fs.list` | List directory |
| GET | `/api/fs/find` | `fs.find` | Find files |
| POST | `/api/experimental/fs/write` | `experimental.fs.write` | Write file |
| GET | `/api/command` | `command.list` | List commands |
| GET | `/api/skill` | `skill.list` | List skills |
| POST | `/api/rpc/{rpcID}/{method}` | `rpc.call` | Call a plugin RPC |
| GET | `/api/event` | `event.subscribe` | Subscribe to events |
| GET | `/api/pty` | `pty.list` | List PTY sessions |
| POST | `/api/pty` | `pty.create` | Create PTY session |
| GET | `/api/pty/{ptyID}` | `pty.get` | Get PTY session |
| PUT | `/api/pty/{ptyID}` | `pty.update` | Update PTY session |
| DELETE | `/api/pty/{ptyID}` | `pty.remove` | Remove PTY session |
| POST | `/api/pty/{ptyID}/connect-token` | `pty.connect.token` | Create PTY WebSocket token |
| GET | `/api/pty/{ptyID}/connect` | `pty.connect` | Connect to PTY session |
| GET | `/api/experimental/session/{sessionID}/terminal/read` | `server.experimental.persistentPty.read` | Read the session's most recently controlled terminal |
| GET | `/api/experimental/session/{sessionID}/terminal` | `server.experimental.persistentPty.list` |  |
| POST | `/api/experimental/session/{sessionID}/terminal` | `server.experimental.persistentPty.create` |  |
| POST | `/api/experimental/persistent-pty/shutdown` | `server.experimental.persistentPty.shutdown` |  |
| POST | `/api/experimental/persistent-pty/handoff` | `server.experimental.persistentPty.handoff` |  |
| GET | `/api/experimental/persistent-pty/{ptyID}` | `server.experimental.persistentPty.get` |  |
| PUT | `/api/experimental/persistent-pty/{ptyID}` | `server.experimental.persistentPty.update` |  |
| DELETE | `/api/experimental/persistent-pty/{ptyID}` | `server.experimental.persistentPty.remove` |  |
| GET | `/api/experimental/persistent-pty/{ptyID}/snapshot` | `server.experimental.persistentPty.snapshot` |  |
| POST | `/api/experimental/persistent-pty/{ptyID}/connect-token` | `server.experimental.persistentPty.connectToken` |  |
| GET | `/api/experimental/persistent-pty/{ptyID}/connect` | `persistentPty.connect` | Connect to a persistent PTY |
| GET | `/api/shell` | `shell.list` | List running shell commands |
| POST | `/api/shell` | `shell.create` | Run shell command |
| GET | `/api/shell/{id}` | `shell.get` | Get shell command |
| DELETE | `/api/shell/{id}` | `shell.remove` | Remove shell command |
| GET | `/api/shell/{id}/output` | `shell.output` | Read shell output |
| GET | `/api/reference` | `reference.list` | List references |
| GET | `/api/worktree` | `worktree.list` | List worktrees |
| POST | `/api/worktree` | `worktree.create` | Create worktree |
| DELETE | `/api/worktree` | `worktree.remove` | Remove worktree |
| POST | `/api/worktree/refresh` | `worktree.refresh` | Refresh worktrees |
| GET | `/api/vcs` | `vcs.get` | VCS info |
| GET | `/api/vcs/base` | `vcs.base` | VCS review base |
| GET | `/api/vcs/status` | `vcs.status` | VCS status |
| GET | `/api/vcs/branch` | `vcs.branch.list` | VCS branches |
| GET | `/api/vcs/diff` | `vcs.diff` | VCS diff |
| GET | `/api/debug/location` | `debug.location.list` | List loaded locations |
| DELETE | `/api/debug/location` | `debug.location.evict` | Evict a loaded location |
| GET | `/api/experimental/migration/v1` | `experimental.migration.v1.status` | Get V1 migration status |
| GET | `/api/websearch/provider` | `websearch.providers` | List web search providers |
| POST | `/api/websearch` | `websearch.query` | Search the web |
| GET | `/api/config` | `config.get` | Get configuration |
| GET | `/api/config/shell` | `config.shells` | List available shells |
| PATCH | `/api/experimental/config` | `experimental.config.update` | Update global configuration |

## Platform scope and boundaries

This platform covers interactive coding, research and writing sessions; local text and vision inference; native project access and permissions; coordinator handoff and evidence guards; AgentMemory and embedding integration; model installation, enrollment and removal; CPU, engine, image and Mesh specialist boundaries; API clients; and Git/Glance documentation publication.

External dependencies — Fedora, the existing k3s and container runtime, the NVIDIA driver, persistent storage, internal DNS/TLS/Traefik, workstation workers, SearXNG and artifact inputs — are consumed through their interfaces; this platform does not prescribe network redesign or host reinstallation. Game engines and purchased asset pipelines keep their own specialist instructions and licenses.

Excluded from automatic operation: production adoption without owner authorization, networking or firewall changes, purchases, exposing secrets, bypassing GPU ownership, resetting state to clear errors, and arbitrary remote-code execution from downloaded model metadata. Public internet exposure and multi-tenant isolation are not qualified features.

## Source map

Paths are relative to `standardised_k3s_project/` unless stated otherwise. The authoritative source always wins over documentation; a mismatch is a finding to investigate, not permission to rewrite live state.

| Subject | Authoritative source |
|---|---|
| Production application/AgentMemory/Toolkit image pins | `ansible/vars/watoom-code.yml` |
| Native app deployment, projects, skills and memory | `ansible/roles/watoom-code/` |
| Inference primary, weights, KV and placement | `manifests/10-infrastructure/llm/llama-cpp-swift-qwen38.yml` |
| Controller runtime and identities | `tools/llm/watoom-gpu-controller/`; `ansible/roles/llm-model-lab/files/gpu-controller.json` |
| Production Python router | `ansible/roles/llm-model-lab/files/gpu-controller-router.py` |
| Model Manager | `tools/model-manager/`; `ansible/playbooks/model-manager.yml` |
| Toolkit worker API | `tools/watoom-toolkit/agent.py` and its contracts |
| Guard, native agents and skills | `ansible/roles/watoom-code/files/` |
| Operator maintenance, backup and release | `tools/watoom-code/` |
| Host GPU cap | `ansible/roles/gpu_host/` |
| Documentation source and renderer | `docs/guide/llm-*.md`; `scripts/render-glance-guide.py` |

The full pinned native API schema, route index, verification metadata and runnable client examples are maintained under `docs/llm-platform/` for Git publication; the download links are above. Source snapshots are references, not replacement services.

## Version and authority

Baseline verified 3 November 2026, Australia/Brisbane: llamAmpere v0.6.2 with the owner-adopted combined turbo profile, 300 W configured cap, fixed MTP depth 5, CUDA graphs and ubatch 1024. Application source is pinned to `786682b1489e92cba4e4b5a277bd49c565c94e4f`. Runtime image pins live in the owning manifests and `ansible/vars/watoom-code.yml`, not in this documentation.

Authority order: live inspected state and acceptance evidence; the exact owning IaC/source and immutable release pins; this documentation; older dated notes. Stable requirements are separated from changeable capacity and tuning values; operators reverify the active profile before maintenance. For related homelab context see the [AI platform](ai.md), [WatooM Code](watoom-code.md), [recovery](recovery.md) and [security](security.md) pages.

For any application, model, routing or controller release: update the owning source first, verify acceptance, refresh the schema from the matching pinned application source, then render, check and verify the served pages. A source commit is not proof of deployment; a pod rollout is not proof of acceptance. Do not publish private runtime configuration, tokens, session contents, image-review grants, databases, weights or raw benchmark prompts.
