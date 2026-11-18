# Godot MCP (NPGameDev toolkit) over a direct restricted SSH connection

Lets watoom-code call `addons/godot_mcp_toolkit` inside the Godot Editor on the rig, through
`@npgamedev/godot-mcp-server`.

```
watoom-code pod --(ssh, forced command)--> rig:2223 (restricted account "godotmcp")
  --> godot-mcp-policy-wrapper.js --> npx @npgamedev/godot-mcp-server (stdio)
  --> WebSocket 127.0.0.1:6550-6560 --> Godot Editor (addons/godot_mcp_toolkit)
```

## Why this looks different from tools/rig-unreal-mcp

Nwiro (Unreal) is already an HTTP MCP server running inside the editor, so that tunnel is a
reverse SSH port-forward plus an HTTP proxy. NPGameDev's bridge is **stdio-only** -- it is spawned
by whatever process wants to talk to it, has no HTTP/SSE option, and only reaches the editor over a
**localhost-only** WebSocket (confirmed from the toolkit's own docs, not from testing a live
editor: no option to bind anywhere but `127.0.0.1`, no remote-host setting). There is therefore no
long-running network server on the rig to tunnel to in the first place.

The only way to reach a stdio program over a network is to have something speak its stdio for it.
SSH already does exactly that (`ssh host command` pipes your local stdin/stdout to the remote
command's stdin/stdout), so here SSH **is** the whole transport: watoom-code's MCP client just runs
`ssh godotmcp@<rig> ...` as a normal "local" MCP server command. This is why this directory has no
relay, no tunnel script, and no HTTP proxy, unlike rig-unreal-mcp.

* The rig runs an SSH **server** for this (unlike rig-unreal-mcp, where the rig only ever makes
  outbound connections). The account (`godotmcp`) is restricted to one `ForceCommand`: whatever the
  client asks for, it only ever runs `node godot-mcp-policy-wrapper.js`, which is the actual gate --
  see below.
* **The policy gate lives on the rig, not the lab.** rig-unreal-mcp's `mcp_proxy.py` is a lab-side
  HTTP proxy that filters tool calls because Nwiro has no gate of its own. Here there is no
  network hop for a lab-side proxy to sit on -- SSH goes straight to the forced command -- so
  `godot-mcp-policy-wrapper.js` filters tool calls on the rig instead, in front of the real bridge.
  Same default-deny mechanism, but as an explicit `allow_names` list (see Notes: the toolkit's real tool
  names do not use list_/read_/find_/get_ prefixes), same re-read-every-request
  `policy.json`, same reasoning: the watoom-code pod never has any other way to reach the rig, so it
  cannot loosen its own policy file either way.
* This route needs an inbound hole in the router for `TheHood -> TRUSTED` that is normally,
  deliberately, blocked (see the deploy runbook). Confirm you actually want that before proceeding.

**UNTESTED against the real editor/plugin/bridge.** `godot-mcp-policy-wrapper.js`'s filtering logic
has its own test (`test-godot-mcp-policy-wrapper.js`, against a fake stand-in child process, not
the real `npx @npgamedev/godot-mcp-server`, pinned to 1.1.2 by `Add-RigAuthorizedKey.ps1 -Version`). Expect to debug the SSH/ForceCommand/Windows-OpenSSH
half of this against the real rig once it is actually run there.

## Install

1. **router** (management VLAN) -- opens exactly one hole in the existing `TheHood -> TRUSTED`
   block, for this one port only, see the deploy runbook for the exact command.
2. **Rig** -- install OpenSSH Server, create the restricted `godotmcp` account, install this
   directory's two scripts, add the lab's public key with its `ForceCommand`, open a scoped Windows
   Firewall rule. See the deploy runbook.
3. **Lab, as root**: `ansible-playbook -i ansible/inventories/homelab/hosts.yml ansible/playbooks/godot-mcp-ssh.yml`
   (generates the lab's SSH key, prints the public key to give the rig, stages
   `/data/ai/watoom-code/config/watoom-tools/godot-mcp-credentials/{key,known_hosts}`). Re-run it
   once the rig's sshd is up so it can learn the rig's host key.
4. **Lab, test the route directly** (before touching watoom-code):
   ```bash
   ssh -i /data/ai/godot-mcp-ssh/key -o UserKnownHostsFile=/data/ai/godot-mcp-ssh/known_hosts \
       -p 2223 godotmcp@10.99.1.44 <<'JSONL'
   {"jsonrpc":"2.0","id":1,"method":"tools/list"}
   JSONL
   ```
   Expect one ndjson line back listing the tools the policy allows (the 36 eager tools with the
   reviewed policy; the on-demand ones appear after `discover_tools`). The Godot Editor
   with the plugin enabled must be open on the rig. The bridge reconnects with backoff (1 s, 2 s,
   4 s ...), so a test that closes stdin immediately only gets one attempt and returns `[]`; hold the
   session open for a few seconds, e.g.
   `( printf initialize+initialized; sleep 6; printf tools/list; sleep 3 ) | ssh ...`.
5. **Enable it in watoom-code** (restarts the pod): set `watoom_code_godot_mcp_enabled: true` in
   `ansible/vars/watoom-code.yml`, run `ansible/playbooks/watoom-code-godot-mcp.yml` (from the
   `ansible/` directory), then `kubectl rollout restart deploy/watoom-code -n watoom-code`. The
   `opencode.json` template is seed-only (`force: false`), so the role task `godot_mcp.yml`
   (`files/enable-godot-mcp.py`) merges the `watoom-godot` entry into the existing config. The
   egress NetworkPolicy is not needed unless `watoom-code-egress.yml` is also applied (see below).

## Rig-side behaviour verified on 2026-11-13 (Windows 10, Win32-OpenSSH 9.5, Godot 4.7.2, toolkit 1.1.2)

These were each hit and fixed on the real rig; `Setup-RigAccount.ps1` and `Add-RigAuthorizedKey.ps1`
encode them. The PowerShell in those two scripts could not be executed from the lab, so a fresh re-run
of the scripts themselves is still untested; the resulting rig configuration is what was verified.

* **Key file location.** `godotmcp` never logs on interactively, so it has no profile and sshd resolves
  its home to `C:\Windows` (log: `trying public key file C:\Windows\.ssh/authorized_keys ... No such
  file`, then only `Failed publickey`). The Match block therefore sets
  `AuthorizedKeysFile C:/ProgramData/ssh/godotmcp_authorized_keys`. The file must be owned by
  `BUILTIN\Administrators` (or the user/SYSTEM) with no inherited ACEs.
* **Debugging sshd.** Run as an ordinary admin, `sshd -ddd` cannot resolve users ("not running as
  system") and misleads. Use `SyslogFacility LOCAL0` + `LogLevel DEBUG3` (log file
  `C:\ProgramData\ssh\logs\sshd.log`) and remove both lines afterwards.
* **Forced command is a launcher.** sshd runs the command through `cmd.exe`; a `command=` containing
  several quoted parts fails with `'""' is not recognized`. The account also has no `node`/`npx` on
  PATH, and `spawn('npx')` cannot start `npx.cmd` without a shell, so `run-godot-mcp.cmd` runs
  `node npx-cli.js` directly. Write the launcher from short pieces: a line that wraps when pasted
  becomes a second batch command.
* **Bridge environment.** As `godotmcp` the bridge connects and immediately drops ("authenticating...
  disconnected") because it cannot find the editor's project or token. The launcher sets
  `GODOT_MCP_PROJECT_PATH`, changes into the project, sets `GODOT_MCP_TOKEN_PATH` (the editor's
  per-project `mcp_token` file; `godotmcp` gets Read on that one file only and the token is never
  copied) and `GODOT_MCP_CONFIG_VERSION`. `Add-RigAuthorizedKey.ps1 -ProjectPath <project>
  [-TokenPath <mcp_token>]` generates all of this. The Godot Editor with the toolkit plugin enabled
  must be running (it listens on 127.0.0.1:6550) and `godotmcp` must be able to read the project folder.
* **Node.js** 22+ installed machine-wide (`C:\Program Files\nodejs`); the npm cache for the account is
  `C:\ProgramData\watoom\npm-cache`.

## Notes

* **Policy opened to all tools on 2026-11-13 (owner's decision).** `godot-mcp-policy.reviewed.json` names every
  tool in the toolkit's reference (115 names, including `discover_tools` and `extensions_refresh`), generated from
  the tool reference; `Setup-RigAccount.ps1` installs it. To apply it to an already-set-up rig, copy that file to
  `C:\ProgramData\watoom\godot-mcp-policy.json` (effective on the next request, no restart). To close one tool
  without reverting, put its name in `deny_names` (deny wins). `execute_code` and `node_call_method` can run
  arbitrary code in the editor and reach the toolkit's updater and `.mcp.json` pin (see the toolkit's security
  recommendations); the agent cards tell the models to use them only when no dedicated tool does the job. A tool
  added by a later toolkit update stays blocked until its name is added. The history below describes the earlier
  read-only starting point.
* Earlier read-only start. The default policy is an explicit allow-list with no prefixes. The bridge's tool
  names put the verb mid-name (`scene_get_tree`, `script_read`, `project_get_settings`), so the old
  `list_`/`read_`/`find_`/`get_` prefixes matched none of the 36 tools and `tools/list` was `[]`;
  a prefix such as `get_` would also admit tools that can run script getters
  (`node_get_property`, `scene_query`, ...). Only five were classified read-only on 2026-11-13:
  `script_read`, `project_get_settings`, `editor_get_console`, `debugger_get_log`, `signal_list`
  (`script_read` only accepts project-relative `res://` paths; the toolkit rejects absolute OS paths
  and `..`). To open a specific tool, edit `%ProgramData%\watoom\godot-mcp-policy.json` on the rig
  (add its name to `allow_names`; takes effect on the next request, no restart needed). The
  toolkit reloads its tool set (36 -> 35 registered was observed), so re-check names after toolkit
  updates.
* `execute_code`-style tools (NPGameDev's toolkit can run arbitrary code in the running game) stay
  behind the same gate as everything else -- there is no separate stronger control for them, so
  treat opening them with real caution.
* To cut access at once: remove/rename `C:\ProgramData\ssh\godotmcp_authorized_keys` on the rig, or
  `Disable-LocalUser -Name godotmcp`, or stop the rig's sshd service.
* Tests: `node test-godot-mcp-policy-wrapper.js` in this folder (Node; run on the lab, exercises
  the policy logic against a fake stand-in bridge, not the real one).

## Deploy runbook (exact commands)

Paths: `LAB=watoom-homelab (10.99.20.225)`, `RIG=10.99.1.44`, repo
`/data/github/watoom-standardised-homelab/standardised_k3s_project`.

1. **router, as admin (management VLAN).** The live ruleset already has an explicit, logged block
   for `TheHood -> TRUSTED` (the lab's own VLAN into the rig's). This adds one narrow accept ahead
   of it, for this port only:
   ```routeros
   /ip firewall filter add chain=forward place-before=22 protocol=tcp \
     src-address=10.99.20.225 dst-address=10.99.1.44 dst-port=2223 \
     action=accept comment="fwd: TheHood watoom-code -> rig godot-mcp SSH (restricted command only)"
   /ip firewall filter print detail where chain=forward
   ```
   Confirm the new rule sits *before* rule `fwd: block TheHood -> TRUSTED` in the printed list (rule
   numbers shift after the insert; re-print to check).

2. **Rig (Windows PowerShell, as Administrator).** Run `Setup-RigAccount.ps1` from this folder --
   it's reachable from the rig over the existing `P:\` projects share (see
   `playbooks/projects-share.yml`) at
   `P:\llm\watoom-llm-platform-new-20261112\standardised_k3s_project\tools\rig-godot-mcp\`:
   ```powershell
   P:\llm\watoom-llm-platform-new-20261112\standardised_k3s_project\tools\rig-godot-mcp\Setup-RigAccount.ps1
   ```
   This installs OpenSSH Server, creates the restricted `godotmcp` account, copies
   `godot-mcp-policy-wrapper.js` to `C:\watoom\rig-godot-mcp\`, installs the reviewed policy `godot-mcp-policy.reviewed.json`
   (copy it from this folder) as `C:\ProgramData\watoom\godot-mcp-policy.json`, adds the sshd `Match User godotmcp` block
   (publickey-only, no forwarding, no TTY -- defense in depth alongside `authorized_keys`'
   `command=`), sets sshd to listen on port 2223, and opens a Windows Firewall rule scoped to the
   lab's address only. Safe to re-run. Then in the Godot Editor: install the toolkit
   (`addons/godot_mcp_toolkit`) into the project, enable the plugin in Project Settings, and make
   sure Node.js 22+ is on the rig's PATH for the `npx` the wrapper spawns.

3. **Lab, as root.**
   ```bash
   ansible-playbook -i /data/github/watoom-standardised-homelab/standardised_k3s_project/ansible/inventories/homelab/hosts.yml \
       /data/github/watoom-standardised-homelab/standardised_k3s_project/ansible/playbooks/godot-mcp-ssh.yml
   ```
   Copy the printed public key, then on the rig run (also reachable via `P:\`):
   ```powershell
   P:\llm\watoom-llm-platform-new-20261112\standardised_k3s_project\tools\rig-godot-mcp\Add-RigAuthorizedKey.ps1 `
       -PublicKey 'ssh-ed25519 AAAA... watoom-godot-mcp'
   ```

4. **Lab.** Re-run step 3's playbook once the rig's sshd is up, so it pins the rig's host key into
   `known_hosts`. Then test per "Install" step 4 above.

5. **Lab, enable in watoom-code (restarts the pod, drops open GUI sessions).** Set
   `watoom_code_godot_mcp_enabled: true` in `ansible/vars/watoom-code.yml` (done 2026-11-13), then, from
   `ansible/`:
   ```bash
   ansible-playbook playbooks/watoom-code-godot-mcp.yml
   kubectl rollout restart deploy/watoom-code -n watoom-code
   ```
   **Do not apply `watoom-code-godot-mcp-egress.yml` on its own.** It is a NetworkPolicy that selects
   the watoom-code pod with `policyTypes: [Egress]` and only allows `10.99.1.44:2223`; it is meant to be
   additive to `watoom-code-egress.yml`. As of 2026-11-13 that base policy is not applied and the
   namespace has no NetworkPolicy, so the pod's egress is unrestricted and the route works without
   either file. Applying only the Godot policy would make it the sole egress policy and cut the pod off
   from DNS and the model router. Apply both together, after reviewing `watoom-code-egress.yml`, or
   neither.

To open an edit tool later, add its name to `allow_names` in
`C:\ProgramData\watoom\godot-mcp-policy.json` on the rig (takes effect immediately, no restart). To
switch it all off: set the variable back to `false`, re-run `playbooks/watoom-code-godot-mcp.yml` (it
removes the `watoom-godot` entry) and restart the pod, delete the egress
policy if you applied it (`kubectl delete -f ...watoom-code-godot-mcp-egress.yml`), remove the router rule added in
step 1, and disable/remove the `godotmcp` account on the rig.
