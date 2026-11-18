# Run in an ELEVATED PowerShell on the rig. Creates the key-only maintenance account "migrate" that the lab operator (Claude Code) uses to fix workers, Unreal and Godot
# on the rig. Key-only, accepted only from the lab server address, no TCP forwarding. -Hours N makes it expire after N hours (default 0 = never). -Remove deletes it.
# usage: .\Add-RigMaintenanceAccount.ps1 -PublicKey "<contents of /data/ai/rig-migrate-ssh/key.pub>" -Admin
# Safe to re-run. Remove everything again with:  .\setup-rig.ps1 -Remove
param([Parameter(Mandatory=$true)][string]$PublicKey, [switch]$Admin, [switch]$Remove, [int]$Hours = 0, [string]$ServerIp = "10.99.20.225")
$ErrorActionPreference = "Stop"
$user = "migrate"
$pub  = $PublicKey.Trim()
$cfg  = "$env:ProgramData\ssh\sshd_config"
if ($Remove) {
    Disable-LocalUser $user -ErrorAction SilentlyContinue; Remove-LocalUser $user -ErrorAction SilentlyContinue
    $af = "$env:ProgramData\ssh\administrators_authorized_keys"
    if (Test-Path $af) { (Get-Content $af) | Where-Object { $_ -notmatch "claude-rig-migrate" } | Set-Content $af }
    $keep = $true; $out = foreach ($l in (Get-Content $cfg)) { if ($l -match "migrate-begin") { $keep = $false }; if ($keep) { $l }; if ($l -match "migrate-end") { $keep = $true } }
    Set-Content $cfg $out
    Unregister-ScheduledTask -TaskName "migrate-account-expiry" -Confirm:$false -ErrorAction SilentlyContinue
    Restart-Service sshd
    Write-Host "removed: account, our key, the sshd_config block and the expiry task"; return
}
if (-not (Get-LocalUser $user -ErrorAction SilentlyContinue)) {
    $pw = [Convert]::ToBase64String((1..24 | ForEach-Object { Get-Random -Maximum 256 }) -as [byte[]])  # random, never shown, password login is disabled
    New-LocalUser $user -Password (ConvertTo-SecureString $pw -AsPlainText -Force) -PasswordNeverExpires -Description "temporary Claude migration account" | Out-Null
}
# A rerun must also revive an account that an earlier -Hours expiry task disabled (2026-11-18: "ready" was printed for a disabled
# account and every login was reset during authentication).
Enable-LocalUser $user
if (-not (Get-LocalUser $user).Enabled) { throw "account '$user' is still disabled" }
if ($Admin) { Add-LocalGroupMember Administrators $user -ErrorAction SilentlyContinue }
$uhome = "C:\Users\$user"; New-Item -ItemType Directory -Force "$uhome\.ssh" | Out-Null
if ($Admin) {
    # administrators' keys live in one shared file on Windows OpenSSH; append ours and keep the strict ACL
    $f = "$env:ProgramData\ssh\administrators_authorized_keys"
    if (-not (Test-Path $f) -or -not (Select-String -Path $f -SimpleMatch $pub -Quiet)) { Add-Content $f $pub }
    icacls $f /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F" | Out-Null
} else {
    $f = "$uhome\.ssh\authorized_keys"; Set-Content $f $pub
    icacls $f /inheritance:r /grant "${user}:F" /grant "SYSTEM:F" /grant "Administrators:F" | Out-Null
}
Copy-Item $cfg "$cfg.bak-migrate" -Force
if (-not (Select-String -Path $cfg -SimpleMatch "migrate-begin" -Quiet)) {
    Add-Content $cfg "# migrate-begin`nMatch User $user`n    PasswordAuthentication no`n    AllowTcpForwarding no`n    X11Forwarding no`nMatch User $user Address *,!$ServerIp`n    PubkeyAuthentication no`n# migrate-end"
}
& "$env:SystemRoot\System32\OpenSSH\sshd.exe" -t -f $cfg; if ($LASTEXITCODE -ne 0) { Copy-Item "$cfg.bak-migrate" $cfg -Force; throw "sshd_config test failed, restored the backup" }
Restart-Service sshd
Unregister-ScheduledTask -TaskName "migrate-account-expiry" -Confirm:$false -ErrorAction SilentlyContinue
if ($Hours -gt 0) {
    $when = (Get-Date).AddHours($Hours)
    Register-ScheduledTask -TaskName "migrate-account-expiry" -Trigger (New-ScheduledTaskTrigger -Once -At $when) -User SYSTEM -Action (New-ScheduledTaskAction -Execute powershell.exe -Argument "-NoProfile -Command Disable-LocalUser migrate") | Out-Null
    Write-Host "ready: account '$user' (admin=$([bool]$Admin)), key-only, only from $ServerIp, disabled automatically at $when"
} else {
    Write-Host "ready: account '$user' (admin=$([bool]$Admin)), key-only, only from $ServerIp, no expiry (remove with -Remove)"
}
