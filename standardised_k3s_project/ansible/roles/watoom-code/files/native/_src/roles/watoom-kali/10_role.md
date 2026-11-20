## Verified route: use it directly

- OpenCode MCP server: `watoom-kali`.
- Endpoint inside the permitted OpenCode namespace:
  `http://watoom-kali-workbench-mcp.kali-agent.svc.cluster.local:8088/mcp`.
- Execution container: **`kali-workbench`**. `kali-pentest` is a retired name
  and is absent. The MCP controller's `mcp` container is not the Kali runtime.
- Bare MCP tool: **`watoom_kali_exec`**. In Code Mode, use its exact callable
  path from the current catalog. Resolve that path once if needed, then reuse it.
  Do not guess prefixes, ports, transports or alternate payload shapes.
- Host `localhost:8088` is not the Kubernetes Service. Do not probe guessed URLs.
- The existing namespace policy permits the OpenCode canary. An unregistered
  Codex chat or another namespace does not automatically have this MCP route.
  Report a missing registration or denied connection once, with the actual
  endpoint and error; do not burn turns trying unrelated execution routes.

## WatooM Code execution: use the registered route
The verified Code Mode expression in WatooM Code is:
tools["watoom-kali"].watoom_kali_exec({executable:"nmap",args:["-sn","10.99.30.0/24"],timeout_seconds:300})
For a user-requested live-host discovery scan, use Nmap -sn on precisely the
requested range. Do not run version/service detection or other targets unless
requested. Nmap is installed in Kali, not necessarily in the workspace container.
Never replace a requested Kali/Nmap scan with workspace Bash TCP or Python probes.
Do not search credentials or start another top-level session to reach the tool.
The MCP is already registered; discovery should be one Code Mode search at most.

Code Mode has no timers: setTimeout, setInterval, sleep and imports are unavailable.
Do not write polling loops that call these functions. Submit the scan once,
preserve its job_id, and call tools["watoom-kali"].watoom_kali_job_status with
that exact ID on later tool turns. If a wait is needed, a native workspace shell
command "sleep 15" may schedule the next poll; it must not execute network probes.
A starting/running response is normal and is not a reason to relaunch Nmap.
Finish only after a completed job and actual exit_code/stdout/stderr are observed.
List responsive IPs from actual Nmap output. A timeout or discovery silence does
not prove that an IP or subnet is unreachable or that every silent host is down.

## Exact calls

Executable mode passes an argv array without a shell:

```json
{"executable":"nmap","args":["-sT","-sV","--open","-T3","10.99.30.156"],"timeout_seconds":300}
```

Shell mode supports arbitrary Bash commands and pipelines:

```json
{"shell":"pwd && ls -la","workdir":"/work/files","timeout_seconds":30}
```

Supply exactly one of `executable` or `shell`. `args` belongs only to executable
mode. Do not use `command`, `cmd`, `shell:true`, Docker flags or host paths as
substitute fields. `workdir`, when supplied, must be an absolute Kali-local path.
The default is `/work/files`; persistent files, logs and captures are under
`/work`, backed by host `/data/ai/kali`. GUI HOME is `/work/gui/home`.

`timeout_seconds` is an integer from 1 through 21600. Foreground noninteractive
calls at 90 seconds or less normally return the completed result. Longer calls,
`background:true` and `interactive:true` return a `job_id`; that is not failure.

- `watoom_kali_job_status`: `{"job_id":"<returned 32-hex ID>"}`.
  Reuse the ID. Poll at a useful interval, usually 10–30 seconds for scans or
  long jobs, rather than launching duplicate commands. Inspect `status`,
  `exit_code`, `stdout`, `stderr`, `truncated` and the recorded output paths.
- `watoom_kali_job_input`: `{"job_id":"<ID>","text":"command\n"}`.
  Create the job with `interactive:true` first. Include a newline to submit input.
- `watoom_kali_job_cancel`: `{"job_id":"<ID>"}`. Verify final status afterward.
- `watoom_kali_file_read`: `{"path":"/work/jobs/<ID>/stdout.log","offset":0,"limit":65536,"text":true}`.
  Read bounded chunks rather than repeatedly injecting whole logs.
- `watoom_kali_desktop`: use `action` equal to `start`, `status`, `windows`,
  `screenshot`, `click`, `type` or `key`, with the corresponding `x`, `y`,
  `button`, `text` or `key` fields. Launch GUI programs through the exec tool
  with `background:true`; the runtime already provides DISPLAY and persistence.
- `watoom_kali_installed_reference`:
  `{"tool":"nmap","task":"<specific syntax question>"}`. Use installed
  reference/help only when syntax is uncertain; do not rediscover known calls.

## Evidence and efficient failure handling

Run the command the user requested. Preserve the actual argv, job ID, exit code
and result. Do not replace Nmap with Python or change its flags while describing
the result as the original scan. If discovery says "Host seems down", report
that port/service enumeration did not run; do not claim all ports are closed.
A `-Pn` follow-up is a separate command and must be labelled as such.

The verified Nmap repair removes incompatible file capabilities from
`/usr/lib/nmap/nmap`; version 7.99 executes with the existing container
capability boundary, SELinux and seccomp. Do not assume every EPERM is missing
NET_RAW or seccomp. On a new failure, collect the specific error and one
targeted diagnostic; correlate binary permissions/capabilities and audit
evidence before changing security settings. Avoid repeating a failing call
without a changed hypothesis or repair.

Keep work aligned with the user's task, preserve existing files, and distinguish
PASS, FAIL, BLOCKED and NOT TESTED. Reuse durable job logs and relevant memory
checkpoints instead of repeating discovery or copying raw logs into context.


### Metasploit database execution
The target is `kali-workbench`, not the retired `kali-pentest`. Use the registered `watoom_kali_exec` tool. PostgreSQL 18 is already managed by host unit `watoom-kali-metasploit-db.timer`; `msfconsole -q -x 'db_status; workspace; exit -y'` automatically connects to the persistent database. Use a background/interactive job for a long console and poll its job ID. Database data is at /work/postgresql/18-main; credentials are in /work/metasploit/database.yml (never print them). Persistent HOME is /work/gui/home. Do not try msfdb/systemctl/su/sudo/unshare/chown inside the container: system msfdb expects systemd and UID switching, which this container does not provide. If database connectivity fails, report db_status and request the host maintenance helper; do not reset/reinitialize the cluster. Database recovery uses Docker's existing postgres UID, without extra capabilities. Metasploit scanning itself still runs through the general Kali tool.
