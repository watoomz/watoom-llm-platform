<#
.SYNOPSIS
  Rig-side setup for the Godot MCP restricted SSH route (step 2 of README.md's deploy runbook),
  up to but not including the authorized_keys line -- that needs the lab's public key, which the
  lab playbook (godot-mcp-ssh.yml) only prints after this script has installed sshd. Run this
  first, then run Add-RigAuthorizedKey.ps1 once you have that key.
.DESCRIPTION
  Installs OpenSSH Server, creates the restricted non-administrator `godotmcp` account, copies
  godot-mcp-policy-wrapper.js from the P:\ projects share (see playbooks/projects-share.yml) to
  C:\watoom\rig-godot-mcp\, writes the explicit read-only policy.json, adds the sshd Match block and
  dedicated listen port, and opens a Windows Firewall rule scoped to the lab's address only.

  UNTESTED against the real editor/plugin/bridge -- see README.md's caveat. Run from an
  Administrator PowerShell. Safe to re-run: every step either checks first or is naturally
  idempotent (Add-WindowsCapability, Set-Content, Add-NetFirewallRule's -ErrorAction below).
.EXAMPLE
  .\Setup-RigAccount.ps1
  .\Setup-RigAccount.ps1 -LabAddress 10.99.20.225 -Port 2223
#>
[CmdletBinding()]
param(
  [string]$LabAddress = '10.99.20.225',
  [int]$Port = 2223,
  [string]$WrapperSource = '',
  [string]$InstallDir = 'C:\watoom\rig-godot-mcp'
)
$ErrorActionPreference = 'Stop'
if (-not $WrapperSource) {
  $local = Join-Path $PSScriptRoot 'godot-mcp-policy-wrapper.js'
  $WrapperSource = if (Test-Path $local) { $local } else {
    'P:\llm\watoom-llm-platform-new-20261112\standardised_k3s_project\tools\rig-godot-mcp\godot-mcp-policy-wrapper.js'
  }
}
Write-Host "Using wrapper source: $WrapperSource"
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw 'Run this from an Administrator PowerShell.'
}

Write-Host '== OpenSSH Server ==' -ForegroundColor Cyan
if ((Get-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0').State -ne 'Installed') {
  Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
}
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic

Write-Host '== Restricted account: godotmcp ==' -ForegroundColor Cyan
if (-not (Get-LocalUser -Name godotmcp -ErrorAction SilentlyContinue)) {
  $pw = ConvertTo-SecureString (New-Guid).Guid -AsPlainText -Force
  New-LocalUser -Name godotmcp -Password $pw -PasswordNeverExpires -AccountNeverExpires `
      -Description "Restricted: Godot MCP policy wrapper only"
} else {
  Write-Host 'godotmcp already exists, leaving it as is'
}

Write-Host '== Policy wrapper ==' -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item $WrapperSource (Join-Path $InstallDir 'godot-mcp-policy-wrapper.js') -Force
Get-Content (Join-Path $InstallDir 'godot-mcp-policy-wrapper.js') -TotalCount 1

Write-Host '== Policy file ==' -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path C:\ProgramData\watoom | Out-Null
# The reviewed policy is godot-mcp-policy.reviewed.json beside this script: an explicit list of every tool name in the
# toolkit's tool reference (the names put the verb mid-name, e.g. scene_get_tree, so verb prefixes match nothing).
# Opened to all tools by the owner on 2026-11-13; a tool added by a later toolkit update stays blocked until its
# name is added. To close a tool put its name in deny_names (deny wins). Re-copy this file to change the live policy.
$policySource = Join-Path $PSScriptRoot 'godot-mcp-policy.reviewed.json'
if (Test-Path $policySource) {
  Copy-Item $policySource C:\ProgramData\watoom\godot-mcp-policy.json -Force
} else {
  Write-Warning 'godot-mcp-policy.reviewed.json not found beside this script: installing the five-tool read-only baseline.'
  '{"allow_prefixes": [], "allow_names": ["script_read","project_get_settings","editor_get_console","debugger_get_log","signal_list"], "deny_names": []}' `
      | Set-Content C:\ProgramData\watoom\godot-mcp-policy.json
}

Write-Host '== sshd_config: Match block + dedicated port ==' -ForegroundColor Cyan
$sshdConfig = 'C:\ProgramData\ssh\sshd_config'
$current = Get-Content $sshdConfig -Raw
if ($current -notmatch 'Match User godotmcp') {
  Add-Content $sshdConfig @"

Match User godotmcp
    AuthenticationMethods publickey
    PasswordAuthentication no
    AllowTcpForwarding no
    X11Forwarding no
    PermitTTY no
    AuthorizedKeysFile C:/ProgramData/ssh/godotmcp_authorized_keys
Match all
"@
} else {
  Write-Host 'Match User godotmcp block already present, leaving it as is'
}
if ($current -notmatch "(?m)^Port $Port$") {
  Add-Content $sshdConfig "Port $Port"
} else {
  Write-Host "Port $Port already configured"
}
Restart-Service sshd

Write-Host '== Firewall: inbound from the lab only ==' -ForegroundColor Cyan
if (-not (Get-NetFirewallRule -Name sshd-godot-mcp -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -Name sshd-godot-mcp -DisplayName 'OpenSSH Godot MCP (restricted)' `
      -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort $Port -RemoteAddress $LabAddress
} else {
  Write-Host 'sshd-godot-mcp firewall rule already exists, leaving it as is'
}

Write-Host "Done. Next: run the lab playbook (godot-mcp-ssh.yml), then Add-RigAuthorizedKey.ps1 -PublicKey '<printed key>'." -ForegroundColor Green
