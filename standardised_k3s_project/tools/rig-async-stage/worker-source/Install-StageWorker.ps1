param(
  [string]$Root = 'F:\WatooM\workstation-render-stage',
  [string]$Python = 'C:\Users\RIG_USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe',
  [string]$HostAlias = 'lab',
  [ValidateSet('CPU','OPTIX')][string]$Device = 'OPTIX'
)
$ErrorActionPreference = 'Stop'
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$rootPath = [System.IO.Path]::GetFullPath($Root)
$blender = Join-Path $rootPath 'runtime\blender-5.2.1-windows-x64\blender.exe'
$key = Join-Path $rootPath 'keys\rig-stage'
$transferKey = Join-Path $rootPath 'keys\rig-transfer'
$ffmpeg = Join-Path $rootPath 'runtime\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe'
$worker = Join-Path $rootPath 'source\worker.py'
$pythonw = Join-Path (Split-Path $Python) 'pythonw.exe'
foreach ($file in @($Python,$pythonw,$blender,$key,$transferKey,$ffmpeg,$worker)) {
  if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw "Required staged input missing: $file" }
}
$taskName = 'WatooM-Blender-Render-Stage'
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing -and ($existing.Actions.Execute -ne $pythonw)) { throw 'Existing task has another owner/runtime; inspect it before replacement' }
New-Item -ItemType Directory -Force -Path (Join-Path $rootPath 'state') | Out-Null
& icacls (Join-Path $rootPath 'state') /inheritance:r /grant:r "${identity}:(OI)(CI)(F)" | Out-Null
foreach ($privateKey in @($key,$transferKey)) { & icacls $privateKey /inheritance:r /grant:r "${identity}:(R)" | Out-Null }
$config = @{
  native_only = $true; root = (Join-Path $rootPath 'state'); ssh = "$env:WINDIR\System32\OpenSSH\ssh.exe"
  sftp = "$env:WINDIR\System32\OpenSSH\sftp.exe"; sftp_key = $transferKey; sftp_user = 'watoom-render-transfer'; transfer_timeout = 3600; ffmpeg = $ffmpeg
  key = $key; user = 'watoom-render-stage'; host = $HostAlias; blender = $blender; device = $Device
}
$configPath = Join-Path $rootPath 'worker.json'
[System.IO.File]::WriteAllText($configPath,($config | ConvertTo-Json),[System.Text.UTF8Encoding]::new($false))
$arguments = '"{0}" --config "{1}"' -f $worker,$configPath
$action = New-ScheduledTaskAction -Execute $pythonw -Argument $arguments -WorkingDirectory $rootPath
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Opt-in Blender staging jobs over a restricted outbound SSH protocol; one slot, 8GiB Windows Job Object, 900 seconds.' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output "ACTIVATED $taskName device=$Device user=$identity"
