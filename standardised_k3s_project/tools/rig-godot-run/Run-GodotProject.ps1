<#
  Run-GodotProject.ps1 - bring a Godot project up to date from its source folder and run it.

  First run:   Run-GodotProject.ps1 -Source <folder-or-share> [-Name zombie]
  After that:  Run-GodotProject.ps1 -Name zombie            (the source is remembered)

  What it does
    1. Mirrors the source into %LOCALAPPDATA%\WatooM\godot-projects\<Name> with robocopy: only new or changed files are copied, files deleted at the
       source are removed, and the local Godot import cache (.godot) is kept, so a second run takes seconds instead of a full copy.
    2. Skips folders that are never needed to play: .godot, .git, .opencode, .source-backup (plus anything you add with -Exclude).
    3. Handles folders whose names differ only by case (assets / Assets): Windows cannot hold both, so the one the project's scenes and scripts
       actually reference is kept and the other is skipped with a warning (override with -KeepFolder).
    4. Imports if anything changed, then launches Godot on the project.

  Options
    -Console     run the console build in this window so engine messages stay visible (default is the normal windowed build)
    -Editor      open the Godot editor instead of running the game
    -NoSync      run what is already local, without touching the source
    -Check       show what a sync would do (robocopy /L) and stop
    -Exclude     extra folder names to skip, e.g. -Exclude World,Videos
    -KeepFolder  when two folders differ only by case (assets / Assets), keep this one, e.g. -KeepFolder Assets
    -Full        also copy the usually-skipped folders except .git and .godot
    -Reset       delete the local copy first and copy everything again
#>
param(
    [string]$Source,
    [string]$Name,
    [string[]]$Exclude = @(),
    [string[]]$KeepFolder = @(),
    [switch]$Console,
    [switch]$Editor,
    [switch]$NoSync,
    [switch]$Check,
    [switch]$Full,
    [switch]$Reset
)
$ErrorActionPreference = 'Stop'
$base = Join-Path $env:LOCALAPPDATA 'WatooM'
$configDir = Join-Path $base 'godot-run'
$projects = Join-Path $base 'godot-projects'

function Find-Godot([bool]$wantConsole) {
    $known = @()
    if ($env:WATOOM_GODOT) { $known += $env:WATOOM_GODOT }
    $saved = Join-Path $configDir 'godot-path.txt'
    if (Test-Path $saved) { $known += (Get-Content $saved -Raw).Trim() }
    $known += 'F:\WatooM\rig-async-stage-20261026\runtime\godot-4.7.2\Godot_v4.7.2-stable_win64.exe'
    $windowed = $null
    foreach ($c in $known) { if ($c -and (Test-Path $c)) { $windowed = (Resolve-Path $c).Path; break } }
    if (-not $windowed) {
        foreach ($root in @('F:\WatooM\rig-async-stage-20261026\runtime', "$env:ProgramFiles\Godot", 'C:\Godot')) {
            if (Test-Path $root) {
                $f = Get-ChildItem -Path $root -Recurse -Depth 3 -Filter 'Godot_v*_win64.exe' -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch 'console' } | Select-Object -First 1
                if ($f) { $windowed = $f.FullName; break }
            }
        }
    }
    if (-not $windowed) {
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object System.Windows.Forms.OpenFileDialog
        $dialog.Title = 'Where is Godot 4.7 (Godot_v*_win64.exe)?'
        $dialog.Filter = 'Godot (Godot*.exe)|Godot*.exe'
        if ($dialog.ShowDialog() -ne 'OK') { throw 'Godot was not found. Set WATOOM_GODOT to the full path of Godot_v4.7.2-stable_win64.exe.' }
        $windowed = $dialog.FileName
        New-Item -ItemType Directory -Force -Path $configDir | Out-Null
        Set-Content -Path $saved -Value $windowed
    }
    $consoleExe = $windowed -replace '_win64\.exe$', '_win64_console.exe'
    if ($wantConsole -and (Test-Path $consoleExe)) { return $consoleExe }
    return $windowed
}

# Folders that differ only by case cannot coexist on Windows, and a Windows client cannot even walk them reliably (a path built through one name can land in the
# other and fail). So the colliding folders are never scanned: which one the project uses is decided from files OUTSIDE them (project.godot, scenes,
# scripts...), where paths are unambiguous. robocopy matches names case-insensitively, so every colliding folder is excluded from the main pass and the kept
# one is copied on its own afterwards. -KeepFolder overrides the detection.
function Get-CaseCollisions([string]$source, [string[]]$forced) {
    $result = @{ skip = @(); keep = @() }
    $dirs = @(Get-ChildItem -LiteralPath $source -Directory -Force -ErrorAction SilentlyContinue)
    $groups = @($dirs | Group-Object { $_.Name.ToLower() } | Where-Object { $_.Count -gt 1 })
    if (-not $groups) { return $result }
    $colliding = @($groups | ForEach-Object { $_.Group.Name })
    $ignore = @('.godot', '.git', '.opencode', '.source-backup', '.import')
    $wanted = @('.godot', '.tscn', '.tres', '.gd')
    $texts = @(Get-ChildItem -LiteralPath $source -File -Force -ErrorAction SilentlyContinue | Where-Object { $wanted -contains $_.Extension })
    foreach ($other in ($dirs | Where-Object { ($colliding -cnotcontains $_.Name) -and ($ignore -notcontains $_.Name) })) {
        $texts += @(Get-ChildItem -LiteralPath $other.FullName -Recurse -File -Force -ErrorAction SilentlyContinue | Where-Object { $wanted -contains $_.Extension })
    }
    foreach ($group in $groups) {
        $names = @($group.Group.Name)
        $best = $null; $bestCount = -1
        $force = @($forced | Where-Object { $names -contains $_ })
        if ($force.Count -ge 1) { $best = $force[0]; $bestCount = -2 }
        else {
            foreach ($name in ($names | Sort-Object { $_ } -CaseSensitive)) {
                $needle = 'res://' + $name + '/'
                $count = 0
                foreach ($t in $texts) {
                    try { if (Select-String -LiteralPath $t.FullName -SimpleMatch $needle -Quiet -ErrorAction Stop) { $count++ } } catch { }
                }
                if ($count -gt $bestCount) { $best = $name; $bestCount = $count }
            }
        }
        $result.keep += $best
        foreach ($d in $group.Group) { $result.skip += $d.FullName }
        if ($bestCount -eq -2) { Write-Host ("Note: '{0}' exist side by side at the source; keeping '{1}' as you asked (-KeepFolder) and skipping the rest." -f ($names -join "' and '"), $best) -ForegroundColor Yellow }
        elseif ($bestCount -le 0) { Write-Host ("Note: '{0}' exist side by side at the source and no scene or script refers to either. Keeping '{1}' (use -KeepFolder <name> to choose) and skipping the rest." -f ($names -join "' and '"), $best) -ForegroundColor Yellow }
        else { Write-Host ("Note: '{0}' exist side by side at the source; Windows can only hold one. Keeping '{1}' (referenced by {2} project files) and skipping the rest." -f ($names -join "' and '"), $best, $bestCount) -ForegroundColor Yellow }
    }
    return $result
}

try {
    New-Item -ItemType Directory -Force -Path $configDir, $projects | Out-Null
    if (-not $Name -and $Source) { $Name = Split-Path $Source.TrimEnd('\', '/') -Leaf }
    if (-not $Name) {
        $known = @(Get-ChildItem $configDir -Filter '*.json' -ErrorAction SilentlyContinue | ForEach-Object { $_.BaseName })
        if ($known.Count -eq 1) { $Name = $known[0] } else { throw 'Say which project: -Name <name> (and -Source <folder> the first time).' }
    }
    $configFile = Join-Path $configDir ($Name + '.json')
    if (-not $Source -and (Test-Path $configFile)) { $Source = (Get-Content $configFile -Raw | ConvertFrom-Json).source }
    $dest = Join-Path $projects $Name

    if (-not $NoSync) {
        if (-not $Source) { throw "No source known for '$Name'. Run once with -Source <folder-or-share>." }
        $Source = $Source.TrimEnd('\', '/')
        if (-not (Test-Path -LiteralPath $Source)) { throw "Source not reachable: $Source" }
        if (-not (Test-Path -LiteralPath (Join-Path $Source 'project.godot'))) { throw "No project.godot in $Source - is this the project folder?" }
        if ($Reset -and (Test-Path $dest)) { Write-Host "Resetting local copy $dest ..."; Remove-Item -Recurse -Force $dest }
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        # Windows keeps an existing folder's old spelling (assets) when the source says Assets, and Godot's import cache is keyed on the exact path,
        # so a leftover folder with different case breaks every res:// path. Drop such a folder (and the cache) so the sync recreates it correctly.
        if (-not $Check) {
            foreach ($srcDir in @(Get-ChildItem -LiteralPath $Source -Directory -Force -ErrorAction SilentlyContinue)) {
                $stale = @(Get-ChildItem -LiteralPath $dest -Directory -Force -ErrorAction SilentlyContinue | Where-Object { ($_.Name -ieq $srcDir.Name) -and ($_.Name -cne $srcDir.Name) })
                foreach ($old in $stale) {
                    Write-Host ("Local folder '{0}' has different capitalisation from the source '{1}'; recreating it (and the import cache)." -f $old.Name, $srcDir.Name) -ForegroundColor Yellow
                    Remove-Item -Recurse -Force -LiteralPath $old.FullName
                    $cache = Join-Path $dest '.godot'
                    if (Test-Path -LiteralPath $cache) { Remove-Item -Recurse -Force -LiteralPath $cache }
                }
            }
        }
        $skipDirs = @('.godot', '.git')
        if (-not $Full) { $skipDirs += @('.opencode', '.source-backup', '.import') }
        $skipDirs += $Exclude
        $collisions = Get-CaseCollisions $Source $KeepFolder
        $robo = @($Source, $dest, '/MIR', '/MT:16', '/R:1', '/W:1', '/NP', '/NJH', '/XD') + $skipDirs + $collisions.skip + @('/XF', '*.tmp', '*.bak')
        if ($Check) { $robo += '/L' }
        Write-Host "Syncing $Source  ->  $dest"
        Write-Host ('Skipping folders: ' + (($skipDirs + ($collisions.skip | ForEach-Object { Split-Path $_ -Leaf })) -join ', '))
        if (-not $Check) { Write-Host 'First run copies everything (large projects take a while); later runs copy only what changed.' }
        $stamp = Get-Date
        & robocopy @robo
        $code = $LASTEXITCODE
        if ($code -ge 8) { throw "robocopy reported errors (exit $code); see the lines above." }
        if ($Check) { Write-Host 'Check only: nothing was copied.'; exit 0 }
        $changed = ($code -band 3) -ne 0
        foreach ($keepName in $collisions.keep) {
            Write-Host "Copying the kept folder '$keepName' ..."
            & robocopy (Join-Path $Source $keepName) (Join-Path $dest $keepName) /MIR /MT:16 /R:1 /W:1 /NP /NJH /XD .godot | Out-Null
            if ($LASTEXITCODE -ge 8) { throw "Copying '$keepName' failed (robocopy exit $LASTEXITCODE)." }
            if (($LASTEXITCODE -band 3) -ne 0) { $changed = $true }
        }
        Set-Content -Path $configFile -Value (@{ source = $Source; last_sync = $stamp.ToString('s') } | ConvertTo-Json)
        Write-Host ('Sync done in {0:N0}s ({1}).' -f ((Get-Date) - $stamp).TotalSeconds, $(if ($changed) { 'files changed' } else { 'already up to date' }))
    } else {
        $changed = $false
        if (-not (Test-Path (Join-Path $dest 'project.godot'))) { throw "Nothing local yet for '$Name'; run without -NoSync first." }
    }

    $godotWindowed = Find-Godot $false
    $godotRun = Find-Godot ($Console.IsPresent)
    if ($changed -or -not (Test-Path (Join-Path $dest '.godot'))) {
        Write-Host 'Importing resources (first open, or files changed) ...'
        $import = Start-Process -FilePath $godotWindowed -ArgumentList @('--headless', '--path', "`"$dest`"", '--import') -Wait -PassThru -WindowStyle Hidden
        Write-Host "Import finished (exit $($import.ExitCode))."
    }
    $plain = @('--path', $dest)
    if ($Editor) { $plain = @('--editor') + $plain }
    Write-Host ("Starting {0} ..." -f $(if ($Editor) { 'the Godot editor' } else { $Name }))
    if ($Console) { & $godotRun @plain }
    else { Start-Process -FilePath $godotRun -ArgumentList ($plain | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) }
}
catch {
    Write-Host ''
    Write-Host "Could not run the project: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}
