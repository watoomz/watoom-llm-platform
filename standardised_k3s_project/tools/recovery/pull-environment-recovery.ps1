<#
Copy a private environment recovery run through the EXISTING jailed SFTP account.
No pruning, deletion, port changes, new account or service restart. The operator
must first publish a completed run under /export/environment on the server.
Destination must already have a private ACL; these files contain credentials.
#>
param(
    [string]$Destination = 'F:\data\homelab_recovery',
    [string]$HomelabHost = '10.99.20.225',
    [string]$User = 'watoom-backup-pull',
    [string]$Key = "$env:USERPROFILE\.ssh\watoom-backup-pull",
    [Parameter(Mandatory=$true)][ValidatePattern('^\d{8}T\d{6}Z$')][string]$Run
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($Destination).TrimEnd('\')
if (-not (Test-Path -LiteralPath $root -PathType Container)) {
    throw 'Provision the destination directory with a private ACL before copying recovery credentials.'
}
$broadSids = @('S-1-1-0','S-1-5-11','S-1-5-32-545')
foreach ($rule in (Get-Acl -LiteralPath $root).Access) {
    $sid = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
    if ($rule.AccessControlType -eq 'Allow' -and $sid -in $broadSids -and
        ($rule.FileSystemRights -band [Security.AccessControl.FileSystemRights]::ReadData)) {
        throw 'Destination permits broad read access; use a private owner-controlled backup directory.'
    }
}
function Child([string]$relative) {
    $value = [IO.Path]::GetFullPath((Join-Path $root $relative))
    if (-not $value.StartsWith($root + '\',[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Backup path escapes the declared destination.'
    }
    return $value
}
function Sftp([string[]]$commands) {
    $batch = New-TemporaryFile
    try {
        Set-Content -LiteralPath $batch.FullName -Value $commands -Encoding ascii
        & sftp.exe -q -b $batch.FullName -i $Key -o BatchMode=yes -o StrictHostKeyChecking=yes "$User@$HomelabHost"
        if ($LASTEXITCODE -ne 0) { throw 'Private recovery SFTP operation failed; partial evidence was retained.' }
    } finally {
        Remove-Item -LiteralPath $batch.FullName -Force
    }
}
$final = Child $Run
$partial = Child ('.partial-' + $Run)
if ((Test-Path -LiteralPath $final) -or (Test-Path -LiteralPath $partial)) {
    throw 'Run or partial directory already exists; verify/reconcile it rather than overwriting or deleting it.'
}
New-Item -ItemType Directory -Path $partial | Out-Null
$localManifest = Join-Path $partial 'manifest.json'
Sftp @("get /export/environment/$Run/manifest.json `"$localManifest`"")
$manifest = Get-Content -LiteralPath $localManifest -Raw | ConvertFrom-Json
$commands = @()
foreach ($property in $manifest.files.PSObject.Properties) {
    $name = $property.Name
    if ($name -notmatch '^[A-Za-z0-9_./-]+$' -or $name.StartsWith('/') -or '..' -in ($name -split '/')) {
        throw 'Unsafe remote manifest path.'
    }
    if ($property.Value -notmatch '^[a-f0-9]{64}$') { throw 'Invalid manifest checksum.' }
    $local = Child ('.partial-' + $Run + '\' + ($name -replace '/','\'))
    New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($local)) | Out-Null
    $commands += "get /export/environment/$Run/$name `"$local`""
}
if ($commands.Count -eq 0) { throw 'Empty recovery manifest.' }
Sftp $commands
$files = [ordered]@{}
foreach ($property in $manifest.files.PSObject.Properties) {
    $local = Child ('.partial-' + $Run + '\' + ($property.Name -replace '/','\'))
    $actual = (Get-FileHash -LiteralPath $local -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $property.Value) { throw 'Recovery checksum mismatch; partial evidence retained.' }
    $files[$property.Name] = $actual
}
$receipt = [ordered]@{run=$Run;files=$files;verified_manifest=(Get-FileHash -LiteralPath $localManifest -Algorithm SHA256).Hash.ToLowerInvariant();time=(Get-Date -Format o)}
$receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $partial '.verified') -Encoding utf8
# Both resolved paths were checked against the declared root. No existing run is replaced.
Rename-Item -LiteralPath $partial -NewName $Run
Sftp @("put `"$(Join-Path $final '.verified')`" /receipts/environment/$Run.json")
Write-Output "PASS private off-host recovery run $Run verified ($($files.Count) files). Full service restoration is a separate drill."
