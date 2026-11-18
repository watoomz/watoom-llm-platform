# Isolated homelab development

The `watoom-dev` primary agent is an opt-in development role for
`/data/ai/projects/homelab-dev`. Existing production roles and inference remain
unchanged. Use this role only with the dev project. The Prompt Builder's
Development pipeline can prepare the task; review its scope and copy it into a
new dev session.

## Baseline and integration

An operator validates and normally fast-forwards the existing GitHub `main`, then
`dev`, to the same exact SHA before preparation. Divergent branches are preserved;
never reset or force-push them. The initializer rechecks both authenticated remote
refs and verifies the fresh clone's initial HEAD. Its permanent initial-baseline
receipt records the initial equality even after development advances.

The authenticated GitHub audit found no classic rules or rulesets. GitHub reports
that this private repository's plan does not enforce rulesets. The production
personal SSH identity is therefore never delegated. Agents push to a separate
local bare repository through a dedicated forced-command identity. A root-owned
server receive policy permits only non-deleting fast-forward `dev` updates and
rejects `main`, `master`, tags and all other refs. Production integration requires
separate operator review, validation and authorization; it is never automatic.

## Enforced boundaries and safe defaults

The only development execution tool is `watoom_dev_workspace`. The native plugin
checks the selected role and project, and wraps every tool leaf to deny ordinary
shell, file, MCP, specialist and delegation tools for this role. Project-scoped
native AgentMemory recall remains available. After a verified dev push, report invokes the existing native `/remember`
command for the recipe; lifecycle memory retains execution references. The agent's final summary must contain the
actual commit, test command and receipt, rather than an unverified claim.

A scoped SSH key accepts only the fixed root-owned JSON entry point. Arbitrary
commands run as a dedicated unprivileged OS identity in bubblewrap, with private
PID, network and device namespaces; no production mounts, host credentials,
Kubernetes or Docker socket, GPU devices or writable Git metadata are supplied.
The environment is cleared. CPU defaults to two cores, memory 2 GiB, 64 tasks and
120 seconds per command, with 512 MiB temporary storage and a 5 GiB admission
reserve. Existing host tools are available read-only; tests must use existing or
vendored dependencies. Dependencies requiring downloads need separate operator
preparation. The global task lock serializes development operations.

`commit` accepts at most 30 explicit files after successful validation bound to
the exact working-tree fingerprint and HEAD. `push` is a fixed Git invocation to
the dedicated dev destination, with a scoped key mounted only for that operation.
Client hooks are disabled. The canonical Git config and server hooks are owned by
root. Local hooks, role prose and wrappers alone are not the isolation boundary.

## Maintained deployment and recovery

Run from the authoritative project root after the final production and remote dev
baseline have been verified:

```sh
sudo python3 tools/watoom-code/deploy-platform.py --dev-workspace-only \
  --iac-root "$PWD" --baseline VERIFIED_SHA --host 10.99.20.225 \
  --evidence /data/ai/helper-scripts/audits/llm-dev-setup-TIMESTAMP/install --i-approve
```

The existing Ansible role creates only dev identities, constrained transport,
clone, immutable plugin package and recovery timer. Native activation uses the
existing idle admission guard without restarting the app. A separate systemd
unit and ExecStopPost finalizer restore only owned native config bytes, preserve
the staged agent as rollback evidence, disable the backend and release only its
own fence if activation is interrupted. Unexpected concurrent edits are retained.

Runtime task records are atomic under
`/data/ai/helper-scripts/dev-workspace/state/tasks/JOB`. Each command has an
independent bounded systemd unit and root exit receipt. The recovery timer
quarantines interrupted operations without deleting files or replaying commits.
One explicit retry is permitted after inspecting a failed command. Reuse the same
job and native session; cross-session adoption is denied.

```sh
sudo python3 -I /data/ai/helper-scripts/dev-workspace/runtime.py --recover-all
sudo python3 -I /data/ai/helper-scripts/dev-workspace/activation.py --recover
```

These reconcile owned dev receipts and an incomplete activation only. They do not
reset repositories, restore an old live database or stop production services.
For a completed installation, disable new backend requests by atomically setting
`enabled=false` in the private runtime config after existing dev work is idle;
preserve all clone, Git server, state and evidence. Re-enabling or production
integration requires operator inspection.

## Validation

Run the focused Python and Node tests in `tools/watoom-code/dev_workspace`, then
the affected playbook syntax check and task-file lint from `ansible`. Actual
acceptance must additionally prove restricted SSH, positive read/edit/test/commit
and dev push, remote rejection of main/master, denied production filesystem,
secrets, Kubernetes, network and GPU access, AgentMemory reuse, independent
interruption recovery and unchanged production health. Unit tests or a local Git
hook alone do not establish production isolation PASS. Retain the timestamped
six-file audit state and all runtime receipts.
