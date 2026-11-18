<#
 Installs the Unreal lane worker on the RIG. Run once, in an elevated-NOT-required user session, from the folder holding the built bundle
 (python3 build_lane.py on the homelab, then copy that folder to the rig).
 Order of operations: verify bundle -> pin the installed Unreal (writes unreal-runtime-provenance.json) -> write config -> register + start the task.
 The lane is OUTBOUND ONLY: it polls the homelab's transfer jail and never listens on a port.
#>
param(
  [Parameter(Mandatory)][string]$UnrealRoot,                 # e.g. 'C:\Program Files\Epic Games\UE_5.8'
  [int]$MemoryGiB = 12,                                     # Job Object limit for Unreal (owner-set 2026-11-07: 12). The RIG's other workers use 8; raise it here if a job is killed for memory
  [string]$Root = 'F:\WatooM\unreal-lane',
  [string]$Python = 'C:\Users\watoom\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe',
  [string]$HostAlias = 'lab',
  [string]$StageRoot = 'F:\WatooM\workstation-render-stage',   # where the existing Blender worker keeps its key and state
  [string[]]$BusyJournals = @('F:\WatooM\workstation-render-stage\state\active.private.json')
)
$ErrorActionPreference = 'Stop'
if ($MemoryGiB -lt 8 -or $MemoryGiB -gt 256) { throw 'MemoryGiB must be between 8 and 256' }
$bundle = $PSScriptRoot
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$rootPath = [System.IO.Path]::GetFullPath($Root)
$transferKey = Join-Path $StageRoot 'keys\rig-transfer'
$pythonw = Join-Path (Split-Path $Python) 'pythonw.exe'
foreach ($file in @($Python,$pythonw,$transferKey,(Join-Path $UnrealRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'),(Join-Path $bundle 'unreal_worker.py'))) {
  if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw "Required input missing: $file" }
}
# 1. the bundle must match its own provenance
$prov = Get-Content (Join-Path $bundle 'unreal-lane-provenance.json') -Raw | ConvertFrom-Json
foreach ($p in $prov.files.PSObject.Properties) {
  $h = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $bundle $p.Name)).Hash.ToLower()
  if ($h -ne $p.Value) { throw "Bundle file changed: $($p.Name)" }
}
# 1b. an installed worker keeps running its OLD code until it is stopped (a started task is ignored while an instance runs): refuse while it is mid-job, else stop it
$taskName = 'WatooM-Unreal-Lane'
$running = @(Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" | Where-Object { $_.CommandLine -like '*unreal_worker.py*' })
$journalPath = Join-Path (Join-Path $rootPath 'state') 'active.json'
if ($running.Count -gt 0 -and (Test-Path -LiteralPath $journalPath)) {
  $phase = (Get-Content -LiteralPath $journalPath -Raw | ConvertFrom-Json).phase
  if (@('FETCHING','RUNNING','UPLOADING') -contains $phase) { throw "A lane job is active ($phase); wait for it to finish, then rerun the installer" }
}
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue }
foreach ($proc in $running) { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 3
# 2. copy to the install root, then pin THIS Unreal install
$source = Join-Path $rootPath 'source'
New-Item -ItemType Directory -Force -Path $source, (Join-Path $rootPath 'state') | Out-Null
& icacls (Join-Path $rootPath 'state') /inheritance:r /grant:r "${identity}:(OI)(CI)(F)" | Out-Null
Copy-Item -Force -Path (Join-Path $bundle '*') -Destination $source
& $Python (Join-Path $source 'pin_unreal.py') --ue-root $UnrealRoot
if ($LASTEXITCODE -ne 0) { throw 'Pinning Unreal failed' }
# 3. config (no secrets: the transfer key stays where the existing worker keeps it)
$config = @{
  root = (Join-Path $rootPath 'state'); sftp = "$env:WINDIR\System32\OpenSSH\sftp.exe"; sftp_key = $transferKey; sftp_user = 'watoom-render-transfer'
  host = $HostAlias; transfer_timeout = 3600; memory_gib = $MemoryGiB; poll_seconds = 15; busy_journals = $BusyJournals
  plugins = @('MetaHumanCharacter','MetaHumanCreator','MetaHuman','MetaHumanSDK','RigLogic')
  control_file = (Join-Path (Split-Path $StageRoot) 'worker-control.json')
}
$configPath = Join-Path $rootPath 'unreal-worker.json'
[System.IO.File]::WriteAllText($configPath,($config | ConvertTo-Json),[System.Text.UTF8Encoding]::new($false))
# 4. scheduled task
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing -and ($existing.Actions.Execute -ne $pythonw)) { throw 'Existing task has another owner/runtime; inspect it before replacement' }
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"{0}" --config "{1}"' -f (Join-Path $source 'unreal_worker.py'),$configPath) -WorkingDirectory $source
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Outbound-only Unreal lane: polls the homelab transfer jail for fixed jobs' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output "ACTIVATED $taskName memory=${MemoryGiB}GiB user=$identity"
