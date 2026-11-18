@echo off
rem Drag an asset (file or folder) onto this file, or double-click it to pick one.
rem Add --editor as the last argument via the PowerShell script if you want the Godot editor instead of the viewer.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Open-InGodot.ps1" %*
