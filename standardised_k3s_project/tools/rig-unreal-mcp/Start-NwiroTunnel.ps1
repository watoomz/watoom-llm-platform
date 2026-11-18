<#
.SYNOPSIS
  Keeps a reverse SSH tunnel from this rig to the homelab so watoom-code can reach the Nwiro MCP server in the Unreal Editor.
.DESCRIPTION
  Nwiro listens on 127.0.0.1:5353 inside the editor. This script opens an OUTBOUND connection to the lab and asks the lab to listen on
  127.0.0.1:15353 and forward that to the local 5353. Nothing listens on the rig's network interfaces. The lab account can do nothing but this
  one port forward (no shell, no file access). Run it while the Unreal Editor is open; close the window to cut access.
  First run creates a dedicated key and prints the public key: give that line to the lab (see README) and run again.
.EXAMPLE
  .\Start-NwiroTunnel.ps1 -LabHost 10.99.20.225
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$LabHost,
  [string]$LabUser = 'rigtunnel',
  [int]$LabSshPort = 22,
  [int]$RemotePort = 15353,
  [int]$LocalPort = 5353,
  [string]$KeyPath = (Join-Path $env:USERPROFILE '.ssh\watoom_unreal_tunnel')
)
$ErrorActionPreference = 'Stop'
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { throw 'ssh.exe not found. Install the Windows "OpenSSH Client" optional feature.' }
New-Item -ItemType Directory -Force -Path (Split-Path $KeyPath) | Out-Null
if (-not (Test-Path $KeyPath)) {
  & ssh-keygen -t ed25519 -N '""' -C 'watoom-unreal-tunnel' -f $KeyPath | Out-Null
  Write-Host 'Created a new tunnel key. Give this public key line to the lab, then run this script again:' -ForegroundColor Yellow
  Get-Content "$KeyPath.pub"
  return
}
$delay = 5
while ($true) {
  if (-not (Test-NetConnection -ComputerName 127.0.0.1 -Port $LocalPort -InformationLevel Quiet -WarningAction SilentlyContinue)) {
    Write-Host "Nothing is listening on 127.0.0.1:$LocalPort. Open the Unreal Editor with the Nwiro Integration Kit enabled; retrying in ${delay}s." -ForegroundColor Yellow
    Start-Sleep -Seconds $delay; continue
  }
  Write-Host ("{0} tunnel up: lab 127.0.0.1:{1} -> this rig 127.0.0.1:{2}" -f (Get-Date -Format s), $RemotePort, $LocalPort)
  $started = Get-Date
  & ssh -N -T -i $KeyPath -p $LabSshPort `
    -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new `
    -o IdentitiesOnly=yes -o BatchMode=yes `
    -R "127.0.0.1:${RemotePort}:127.0.0.1:${LocalPort}" "$LabUser@$LabHost"
  $ran = ((Get-Date) - $started).TotalSeconds
  $delay = if ($ran -gt 60) { 5 } else { [Math]::Min($delay * 2, 120) }
  Write-Host ("{0} tunnel closed after {1:N0}s (ssh exit {2}); reconnecting in {3}s" -f (Get-Date -Format s), $ran, $LASTEXITCODE, $delay) -ForegroundColor Yellow
  Start-Sleep -Seconds $delay
}
