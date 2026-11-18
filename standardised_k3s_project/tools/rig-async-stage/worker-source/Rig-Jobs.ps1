param(
 [ValidateSet('Pause','Resume','Status')][string]$Action='Status',
 [ValidateSet('Now','Finish')][string]$Mode='Now',
 [string]$Control='F:\WatooM\workstation-render-stage\worker-control.json',
 [switch]$Quiet
)
$ErrorActionPreference='Stop'
$controlPath=[IO.Path]::GetFullPath($Control)
if (!(Test-Path -LiteralPath (Split-Path $controlPath) -PathType Container)) {throw 'Worker directory missing'}
if ($Action -ne 'Status') {
 $value=@{paused=($Action -eq 'Pause');mode=$Mode.ToLowerInvariant();requested_at=[DateTimeOffset]::UtcNow.ToString('o');requested_by=[Security.Principal.WindowsIdentity]::GetCurrent().Name}
 $temporary=$controlPath+'.'+[Guid]::NewGuid().ToString('N')+'.tmp'
 [IO.File]::WriteAllText($temporary,($value|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
 if (Test-Path -LiteralPath $controlPath) {
  $history=Join-Path (Split-Path $controlPath) 'control-history'
  New-Item -ItemType Directory -Force -Path $history | Out-Null
  [IO.File]::Replace($temporary,$controlPath,(Join-Path $history ([Guid]::NewGuid().ToString('N')+'.json')))
 } else {[IO.File]::Move($temporary,$controlPath)}
}
$state=if(Test-Path -LiteralPath $controlPath){Get-Content -LiteralPath $controlPath -Raw|ConvertFrom-Json}else{@{paused=$false}}
$lines=@()
if($state.paused){$lines+='RIG workers: pause requested ('+$state.mode+'). No new jobs will start.'}else{$lines+='RIG workers: enabled. Queued work can start.'}
foreach($entry in @(@('Blender','F:\WatooM\workstation-render-stage\state\active.private.json'),@('Game','F:\WatooM\rig-async-stage-20261026\state\active.private.json'))) {
 if(Test-Path -LiteralPath $entry[1]){$journal=Get-Content -LiteralPath $entry[1] -Raw|ConvertFrom-Json;$lines+=($entry[0]+': '+$journal.phase)}else{$lines+=($entry[0]+': idle')}
}
if($state.paused -and $state.mode -eq 'now'){$lines+='Current processes stop at the next worker checkpoint, releasing their GPU memory. File transfers may finish first. Partial attempts are retained.'}
if($state.paused -and $state.mode -eq 'finish'){$lines+='The current job may finish before GPU resources are released.'}
$lines+='Resume explicitly restarts an interrupted operation from its frozen inputs; it does not continue a suspended process.'
$message=$lines -join [Environment]::NewLine
if($Quiet){Write-Output $message}else{Add-Type -AssemblyName System.Windows.Forms;[Windows.Forms.MessageBox]::Show($message,'RIG background jobs')|Out-Null}
