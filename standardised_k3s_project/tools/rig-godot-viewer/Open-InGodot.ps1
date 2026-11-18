<#
  Open-InGodot.ps1 - open a 3D asset (or a Godot-ready folder such as a converted MetaHuman) in a viewer on this PC.

  Usage:   Open-InGodot.ps1 <file-or-folder> [-Editor] [-Reimport]
  Easiest: drag the asset (a .glb/.gltf/.tscn file, or a folder) onto Open-InGodot.bat, or double-click the .bat and pick a file.

  What it does: copies the asset's folder into a small cache project, lets Godot import it (the first open of a big asset takes a while),
  then opens a viewer window: drag = orbit, wheel = zoom, right-drag = pan, F frame, 1-4 shaded/unshaded/wire/normals, L light, B background.
  -Editor opens the Godot editor on the same project instead. Nothing is written outside %LOCALAPPDATA%\WatooM\godot-viewer.
#>
param(
    [Parameter(Position = 0)][string]$Path,
    [switch]$Editor,
    [switch]$Reimport
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$cache = Join-Path $env:LOCALAPPDATA 'WatooM\godot-viewer'
$project = Join-Path $cache 'project'

function Find-Godot {
    # Cheap, known locations first; a recursive search only as a last resort and only in the pinned WatooM folder.
    $known = @()
    if ($env:WATOOM_GODOT) { $known += $env:WATOOM_GODOT }
    $saved = Join-Path $cache 'godot-path.txt'
    if (Test-Path $saved) { $known += (Get-Content $saved -Raw).Trim() }
    $known += 'F:\WatooM\rig-async-stage-20261026\runtime\godot-4.7.2\Godot_v4.7.2-stable_win64.exe'
    foreach ($c in $known) { if ($c -and (Test-Path $c)) { return (Resolve-Path $c).Path } }
    foreach ($root in @('F:\WatooM\rig-async-stage-20261026\runtime', "$env:ProgramFiles\Godot", 'C:\Godot')) {
        if (Test-Path $root) {
            $found = Get-ChildItem -Path $root -Recurse -Depth 3 -Filter 'Godot_v*_win64.exe' -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch 'console' } | Select-Object -First 1
            if ($found) { return $found.FullName }
        }
    }
    return $null
}

function Get-StagePrefix([string]$entry, [string]$folder) {
    # A converted scene (.tscn) names its textures and scripts as res://some/path/..., so the folder has to be staged at the place
    # those paths expect. Find the shortest prefix under which every referenced file exists in the source folder.
    if ([System.IO.Path]::GetExtension($entry).ToLower() -ne '.tscn') { return 'asset' }
    $refs = @()
    foreach ($m in [regex]::Matches((Get-Content -LiteralPath $entry -Raw), 'path="res://([^"]+)"')) { $refs += $m.Groups[1].Value }
    if ($refs.Count -eq 0) { return 'asset' }
    $segments = $refs[0].Split('/')
    for ($k = 0; $k -lt $segments.Count; $k++) {
        $prefix = ($segments[0..($k - 1)] -join '/')
        if ($k -eq 0) { $prefix = '' }
        $all = $true
        foreach ($r in $refs) {
            $inside = if ($prefix) { if ($r.StartsWith($prefix + '/')) { $r.Substring($prefix.Length + 1) } else { $null } } else { $r }
            if (-not $inside -or -not (Test-Path -LiteralPath (Join-Path $folder ($inside -replace '/', '\')))) { $all = $false; break }
        }
        if ($all) { if ($prefix) { return $prefix } else { return '.' } }
    }
    return 'asset'
}

function Pick-Asset {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = 'Pick an asset to open in Godot'
    $dialog.Filter = '3D assets (*.glb;*.gltf;*.tscn;*.scn;*.fbx;*.obj)|*.glb;*.gltf;*.tscn;*.scn;*.fbx;*.obj|All files (*.*)|*.*'
    if ($dialog.ShowDialog() -eq 'OK') { return $dialog.FileName }
    return $null
}

try {
    if (-not $Path) { $Path = Pick-Asset }
    if (-not $Path) { Write-Host 'Nothing chosen.'; exit 0 }
    $item = Get-Item -LiteralPath $Path
    Write-Host 'Looking for Godot ...'
    $godot = Find-Godot
    if ($godot) { Write-Host "Using $godot" }
    if (-not $godot) {
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object System.Windows.Forms.OpenFileDialog
        $dialog.Title = 'Where is Godot 4.7 (Godot_v*_win64.exe)?'
        $dialog.Filter = 'Godot (Godot*.exe)|Godot*.exe'
        if ($dialog.ShowDialog() -ne 'OK') { throw 'Godot was not found. Set WATOOM_GODOT to the full path of Godot_v4.7.2-stable_win64.exe.' }
        $godot = $dialog.FileName
        New-Item -ItemType Directory -Force -Path $cache | Out-Null
        Set-Content -Path (Join-Path $cache 'godot-path.txt') -Value $godot
    }

    # choose the entry file and the folder to stage
    if ($item.PSIsContainer) {
        $folder = $item.FullName
        $scene = Get-ChildItem -LiteralPath $folder -Filter ($item.Name + '.tscn') -File | Select-Object -First 1
        if (-not $scene) { $scene = Get-ChildItem -LiteralPath $folder -Filter '*.tscn' -File | Select-Object -First 1 }
        if (-not $scene) { $scene = Get-ChildItem -LiteralPath $folder -Include '*.glb', '*.gltf' -File -Recurse | Select-Object -First 1 }
        if (-not $scene) { throw "No .tscn, .glb or .gltf found in $folder" }
        $entry = $scene.FullName
    } else {
        $entry = $item.FullName
        $folder = $item.DirectoryName
    }
    $size = (Get-ChildItem -LiteralPath $folder -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    $stageWhole = $size -lt 3GB
    $stamp = '{0}|{1}|{2}' -f $entry, $size, (Get-Item -LiteralPath $entry).LastWriteTimeUtc.Ticks
    $stampFile = Join-Path $project 'asset-stamp.txt'
    $current = if (Test-Path $stampFile) { Get-Content $stampFile -Raw } else { '' }

    # project files (always refreshed from this folder so updates to the viewer apply)
    New-Item -ItemType Directory -Force -Path $project | Out-Null
    foreach ($f in 'project.godot', 'viewer.gd', 'viewer.tscn') { Copy-Item (Join-Path $here "viewer\$f") $project -Force }

    $prefix = Get-StagePrefix $entry $folder
    $assetDir = if ($prefix -eq '.') { $project } else { Join-Path $project ($prefix -replace '/', '\') }
    $stamp = $stamp + '|' + $prefix
    if ($Reimport -or $current.Trim() -ne $stamp) {
        Write-Host "Staging $folder ($([math]::Round($size / 1MB)) MB) ..."
        if ($prefix -ne '.' -and (Test-Path $assetDir)) { Remove-Item -Recurse -Force $assetDir }
        New-Item -ItemType Directory -Force -Path $assetDir | Out-Null
        if ($stageWhole) {
            & robocopy $folder $assetDir /E /XD viewer .godot /NFL /NDL /NJH /NJS /NP | Out-Null
            if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
        } else {
            Copy-Item -LiteralPath $entry -Destination $assetDir -Force
            $folder = $item.DirectoryName
        }
        $cacheDir = Join-Path $project '.godot'
        if (Test-Path $cacheDir) { Remove-Item -Recurse -Force $cacheDir }
        Write-Host 'Importing (the first open of a large asset can take a few minutes) ...'
        $import = Start-Process -FilePath $godot -ArgumentList @('--headless', '--path', "`"$project`"", '--import') -Wait -PassThru -WindowStyle Hidden
        Write-Host "Import finished (exit $($import.ExitCode))."
        Set-Content -Path $stampFile -Value $stamp
    }

    $rel = if ($stageWhole) { $entry.Substring($folder.Length).TrimStart('\', '/') -replace '\\', '/' } else { Split-Path $entry -Leaf }
    $resPath = if ($prefix -eq '.') { 'res://' + $rel } else { 'res://' + $prefix + '/' + $rel }
    Set-Content -Path (Join-Path $project 'entry.txt') -Value $resPath -NoNewline
    Write-Host "Opening $resPath"
    if ($Editor) { Start-Process -FilePath $godot -ArgumentList @('--editor', '--path', "`"$project`"") }
    else { Start-Process -FilePath $godot -ArgumentList @('--path', "`"$project`"") }
}
catch {
    Write-Host ''
    Write-Host "Could not open the asset: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}
