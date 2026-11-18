## Kali execution routing
For a single user-requested Kali or Nmap command, use the registered Kali MCP directly
through Code Mode. For a multi-stage investigation, delegate one bounded package to
the native subagent tool with agent watoom-kali; that child uses this same MCP.
Do not duplicate its scans while waiting. The verified call is tools["watoom-kali"].watoom_kali_exec.
Use the current catalog signature; executable plus args runs inside Kali.
The workspace shell is a different execution environment. Missing Nmap there
does not establish Kali availability. Never substitute Bash/Python subnet probes
for a requested Nmap task, hunt credentials, or create another session merely
to reach Kali. For host discovery on a user-specified IPv4 /24, Nmap -sn performs
discovery only; a nonresponsive address is not proof that the host is absent.
If the MCP is actually missing or fails, report the exact registration/connection
failure once and stop that task rather than guessing another route.

