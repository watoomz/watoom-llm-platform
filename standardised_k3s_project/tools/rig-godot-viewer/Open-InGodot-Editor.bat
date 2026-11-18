@echo off
rem Same as Open-InGodot.bat but opens the Godot editor on the staged project.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Open-InGodot.ps1" -Editor %*
