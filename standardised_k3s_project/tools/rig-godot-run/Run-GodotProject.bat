@echo off
rem Double-click to run the remembered project, or pass options, e.g.:  Run-GodotProject.bat -Source \\server\share\zombie-animal-survival -Name zombie
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Run-GodotProject.ps1" %*
