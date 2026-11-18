<#
Pull verified WatooM-Code backups from the homelab to this machine (off-host copy).

The homelab exposes the newest verified runs read-only to the jailed SFTP account
watoom-backup-pull. Each new run is downloaded, every file is checked against the
run's manifest, and only then is it kept and a receipt uploaded; the homelab alerts
when no recent run has a matching receipt. Uses Windows' built-in OpenSSH client.

Run daily from Task Scheduler, e.g.
  powershell -NoProfile -ExecutionPolicy Bypass -File pull-homelab-backups.ps1
#>
param(
    [string]$Destination = 'F:\data\homelab_backups',
    [string]$HomelabHost = '10.99.20.225',
    [string]$User = 'watoom-backup-pull',
    [string]$Key = "$env:USERPROFILE\.ssh\watoom-backup-pull",
    [int]$Keep = 30
)
$ErrorActionPreference = 'Stop'
$Stamp = '^\d{8}T\d{6}Z$'
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$Log = Join-Path $Destination 'pull.log'
function Log($m) { "$(Get-Date -Format o) $m" | Add-Content -Path $Log; Write-Output $m }

function Invoke-Sftp([string[]]$Commands) {
    $batch = New-TemporaryFile
    try {
        Set-Content -Path $batch -Value $Commands -Encoding ascii
        $out = & sftp.exe -q -b $batch -i $Key -o BatchMode=yes -o StrictHostKeyChecking=yes "$User@$HomelabHost" 2>&1
        if ($LASTEXITCODE -ne 0) { throw "sftp failed ($LASTEXITCODE): $out" }
        return $out
    } finally { Remove-Item $batch -Force }
}

try {
    $remote = Invoke-Sftp @('ls -1 /export') | ForEach-Object { ($_ -split '/')[-1].Trim() } | Where-Object { $_ -match $Stamp } | Sort-Object
    foreach ($run in $remote) {
        $final = Join-Path $Destination $run
        if (Test-Path (Join-Path $final '.verified')) { continue }
        $partial = Join-Path $Destination ".partial-$run"
        if (Test-Path $partial) { Remove-Item -Recurse -Force $partial }
        Invoke-Sftp @("get -r /export/$run `"$partial`"") | Out-Null
        $manifest = Get-Content -Raw (Join-Path $partial 'manifest.json') | ConvertFrom-Json
        $files = [ordered]@{}
        foreach ($p in $manifest.files.PSObject.Properties) {
            $path = Join-Path $partial ($p.Name -replace '/', '\')
            $hash = (Get-FileHash -Algorithm SHA256 -Path $path).Hash.ToLowerInvariant()
            if ($hash -ne $p.Value) { throw "checksum mismatch in $run : $($p.Name)" }
            $files[$p.Name] = $hash
        }
        if (Test-Path $final) { Remove-Item -Recurse -Force $final }
        Rename-Item -Path $partial -NewName $run
        Set-Content -Path (Join-Path $final '.verified') -Value (Get-Date -Format o)
        $receipt = Join-Path $env:TEMP "$run.json"
        [ordered]@{ run = $run; files = $files; host = $env:COMPUTERNAME; time = (Get-Date -Format o) } | ConvertTo-Json -Depth 4 | Set-Content -Path $receipt -Encoding utf8
        Invoke-Sftp @("put `"$receipt`" /receipts/$run.json") | Out-Null
        Remove-Item $receipt -Force
        Log "verified $run ($($files.Count) files)"
    }
    $local = Get-ChildItem -Directory $Destination | Where-Object { $_.Name -match $Stamp -and (Test-Path (Join-Path $_.FullName '.verified')) } | Sort-Object Name
    $local | Select-Object -SkipLast $Keep | ForEach-Object { Remove-Item -Recurse -Force $_.FullName; Log "pruned $($_.Name)" }
} catch {
    Log "FAILED: $_"
    exit 1
}
