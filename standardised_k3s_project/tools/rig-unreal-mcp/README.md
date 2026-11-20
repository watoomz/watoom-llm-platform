# Unreal MCP over a reverse SSH tunnel (Nwiro AI Integration Kit)

Lets watoom-code call the Nwiro MCP server that runs **inside the Unreal Editor on the rig**, without opening any port on the rig.

```
watoom-code pod --Bearer token--> proxy 10.242.0.1:15354 --> lab 127.0.0.1:15353 <==ssh -R== rig 127.0.0.1:5353 (Nwiro, in the editor)
```

* The rig only makes an **outbound** SSH connection. The lab account (`rigtunnel`) has no shell and may only listen on `127.0.0.1:15353`.
* `mcp_proxy.py` is the gate: bearer token, `POST /mcp` only, and a tool policy. The default policy is **read-only** (`list_`, `read_`, `find_`, `get_`).
  Edit `/data/ai/unreal-mcp/policy.json` (root-owned) to open specific tools; it is re-read on every request. Tools that are not allowed are also
  hidden from `tools/list`.
* The editor must be open with the Nwiro Integration Kit enabled. The kit's docs list UE 5.5 to 5.7; its Fab listing says 5.8 support arrived in 1.0.7, so use a recent version.
  Nwiro documents no authentication of its own, which is why the proxy exists.

## Install
1. Lab: `ansible-playbook -i ansible/inventories/homelab/hosts.yml ansible/playbooks/unreal-mcp-tunnel.yml`
   (creates the tunnel-only account, an sshd drop-in validated with `sshd -t`, the token, the policy file and the proxy service).
2. Rig (PowerShell, Windows OpenSSH client installed): `.\Start-NwiroTunnel.ps1 -LabHost <lab address>`. The first run creates a key and prints the public key.
3. Lab: re-run the playbook with that key: `-e "rig_tunnel_public_key='ssh-ed25519 AAAA... watoom-unreal-tunnel'"`
4. Rig: run `.\Start-NwiroTunnel.ps1 -LabHost <lab address>` again and leave it running while you use the editor.
5. Check from the lab: `curl -s -H "Authorization: Bearer $(cat /data/ai/unreal-mcp/token)" -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' http://10.242.0.1:15354/mcp`
6. Enable it in watoom-code (restarts the pod): apply `manifests/10-infrastructure/opencode/watoom-code-unreal-mcp-egress.yml`, then set
   `watoom_code_unreal_mcp_enabled: true` and run the watoom-code playbook. Until this step nothing in the cluster can reach the proxy.

## Notes
* Start read-only. The editor-side permission prompts are documented for the in-editor panel only; a direct MCP client may not be prompted.
  The proxy policy is the control you have.
* Close the tunnel window to cut access at once. `systemctl stop watoom-unreal-mcp-proxy` cuts it from the lab.
* Tests: `python3 -m unittest test_mcp_proxy` in this folder.

## Deploy runbook (exact commands)

Paths: `LAB=homelab-host (10.99.20.225)`, repo `/data/github/watoom-standardised-homelab/standardised_k3s_project`, rig engine `F:\AI\Unreal5.8\UE_5.8`.

1. **Rig (Windows).** Epic Games Launcher > Library > Fab Library: install "NWIRO - AI Integration Kit" and "One-Click Level Generator" to UE 5.8. In the editor
   enable Nwiro Integration Kit, One-Click Level Generator, PythonScriptPlugin, WebBrowserWidget and PCG, then restart. Check `Test-NetConnection 127.0.0.1 -Port 5353` is True.
2. **Lab, as root.**
   `ansible-playbook -i /data/github/watoom-standardised-homelab/standardised_k3s_project/ansible/inventories/homelab/hosts.yml /data/github/watoom-standardised-homelab/standardised_k3s_project/ansible/playbooks/unreal-mcp-tunnel.yml`
3. **Rig.** Copy `Start-NwiroTunnel.ps1` to `F:\AI\helper_scripts\rig-unreal-mcp\` (a copy is also kept at `/data/ai/artifacts/rig-unreal-mcp/` on the lab), then
   `cd F:\AI\helper_scripts\rig-unreal-mcp` and `powershell -ExecutionPolicy Bypass -File .\Start-NwiroTunnel.ps1 -LabHost 10.99.20.225`. The first run prints a public key line.
4. **Lab.** Re-run step 2 with `-e "rig_tunnel_public_key='<that line>'"`.
5. **Rig.** Run the step 3 command again and leave it open while using the editor.
6. **Lab.** Test: `curl -s -H "Authorization: Bearer $(cat /data/ai/unreal-mcp/token)" -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' http://10.242.0.1:15354/mcp`
7. **Lab, enable in watoom-code (restarts the pod, drops open GUI sessions).**
   `kubectl apply -f /data/github/watoom-standardised-homelab/standardised_k3s_project/manifests/10-infrastructure/opencode/watoom-code-unreal-mcp-egress.yml`
   then add `watoom_code_unreal_mcp_enabled: true` to `ansible/vars/watoom-code-production.yml` (`watoom-code.yml` after the rename cutover) and run
   `ansible-playbook -i <inventory as above> /data/github/watoom-standardised-homelab/standardised_k3s_project/ansible/playbooks/watoom-code-production.yml` (`watoom-code.yml` after the rename).

To open edit tools later, add their names to `allow_names` in `/data/ai/unreal-mcp/policy.json` on the lab (takes effect immediately). To switch it all off:
set the variable back to `false` and re-run step 7's playbook, delete the egress policy (`kubectl delete -f ...watoom-code-unreal-mcp-egress.yml`), and `systemctl disable --now watoom-unreal-mcp-proxy`.
