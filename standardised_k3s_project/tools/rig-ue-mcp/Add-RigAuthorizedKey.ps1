<#
.SYNOPSIS
  Installs the lab's public key into uemcp's authorized keys, forced to run only the ue-mcp launcher (policy wrapper in
  front of the ue-mcp server). Run after Setup-RigAccount.ps1 and after the lab playbook (ue-mcp-ssh.yml) has printed the key.
.DESCRIPTION
  Same mechanics as tools/rig-godot-mcp/Add-RigAuthorizedKey.ps1, which was debugged on this rig (read its comments for why):
  the account has no profile so sshd resolves its home to C:\Windows (hence AuthorizedKeysFile under ProgramData, owned by
  BUILTIN\Administrators with tight ACLs); cmd.exe mangles a multi-quoted forced command (hence a launcher .cmd); the account
  has a minimal PATH (hence absolute node paths); spawn('npx') needs a shell (hence `node npx-cli.js`).
  Differences for ue-mcp: it is pinned to -Version (never @latest, which would run whatever was published last), it needs the
  .uproject path, and it keeps state under the user's home, so HOME/USERPROFILE point at a writable ProgramData folder.

  Before this: on the rig, in the Unreal project folder, with the editor CLOSED, run `npx ue-mcp init` once as your own user
  (it installs the UE_MCP_Bridge plugin into the project and writes ue-mcp.yml), then open the editor.

  UNTESTED on the rig and against the real server -- see README.md.
.EXAMPLE
  .\Add-RigAuthorizedKey.ps1 -PublicKey 'ssh-ed25519 AAAAC3... watoom-ue-mcp' -UProject F:\Unreal\MyGame\MyGame.uproject
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$PublicKey,
  [Parameter(Mandatory)][string]$UProject,
  [string]$Version = '1.4.14',
  # The Windows user the Unreal Editor runs as (it writes the bridge session token); defaults to whoever runs this script.
  [string]$EditorUser = $env:USERNAME,
  [string]$TokenDir = 'C:\ProgramData\watoom\ue-mcp-bridge-tokens',
  [string]$WrapperPath = 'C:\watoom\rig-ue-mcp\ue-mcp-policy-wrapper.js',
  [string]$NodePath = (Get-Command node -ErrorAction SilentlyContinue).Source
)
$ErrorActionPreference = 'Stop'
if (-not (Get-LocalUser -Name uemcp -ErrorAction SilentlyContinue)) { throw 'uemcp does not exist yet -- run Setup-RigAccount.ps1 first.' }
if (-not $NodePath -or -not (Test-Path $NodePath)) { throw 'node.exe not found: install Node.js 20+ machine-wide, or pass -NodePath <full path to node.exe>.' }
if ($PublicKey -notmatch '^ssh-') { throw "That doesn't look like a public key line (ssh-ed25519/ssh-rsa/...). Paste exactly what the lab playbook printed." }
if ($Version -notmatch '^\d+\.\d+\.\d+([-.][0-9A-Za-z.]+)?$') { throw "-Version must be an exact version like 1.4.14, not a range or a tag." }
if (-not (Test-Path -LiteralPath $UProject) -or [IO.Path]::GetExtension($UProject) -ne '.uproject') { throw "UProject must be the full path of an existing .uproject file: $UProject" }
$projectDir = Split-Path $UProject
if (-not (Test-Path (Join-Path $projectDir 'Plugins\UE_MCP_Bridge'))) {
  Write-Warning "Plugins\UE_MCP_Bridge not found in $projectDir -- run 'npx ue-mcp init' in the project (editor closed) first, or the editor will have no bridge."
}

$authorizedKeys = 'C:\ProgramData\ssh\uemcp_authorized_keys'
$nodeDir = Split-Path $NodePath
$npxCli = Join-Path $nodeDir 'node_modules\npm\bin\npx-cli.js'
if (-not (Test-Path $npxCli)) { throw "npx-cli.js not found at $npxCli -- pass the node.exe of a standard Node.js install." }
$npmCache = 'C:\ProgramData\watoom\npm-cache-ue'
$home_ = 'C:\ProgramData\watoom\ue-mcp-home'
New-Item -ItemType Directory -Force -Path $npmCache, $home_ | Out-Null
icacls $npmCache /grant 'uemcp:(OI)(CI)M' | Out-Null
icacls $home_ /grant 'uemcp:(OI)(CI)M' | Out-Null
# ue-mcp reads the project and writes its own state/logs beside it (location not verified): read on the project, modify on Saved only.
icacls $projectDir /grant 'uemcp:(OI)(CI)RX' | Out-Null
# The bridge refuses clients without a session token that the editor writes when it starts (default: under the editor user's
# home, which uemcp cannot read). Both sides must use the same UE_MCP_BRIDGE_TOKEN_DIR: the editor writes here, uemcp may only read.
New-Item -ItemType Directory -Force -Path $TokenDir | Out-Null
icacls $TokenDir /inheritance:r | Out-Null
icacls $TokenDir /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' ($EditorUser + ':(OI)(CI)M') 'uemcp:(OI)(CI)R' | Out-Null
$saved = Join-Path $projectDir 'Saved'
New-Item -ItemType Directory -Force -Path $saved | Out-Null
icacls $saved /grant 'uemcp:(OI)(CI)M' | Out-Null

$launcher = Join-Path (Split-Path $WrapperPath) 'run-ue-mcp.cmd'
$node = '"' + $NodePath + '"'
# Built from short pieces and written as exactly these lines: a wrapped/split line becomes a separate batch command.
@('@echo off',
  ('set "PATH=' + $nodeDir + ';%PATH%"'),
  ('set "npm_config_cache=' + $npmCache + '"'),
  ('set "HOME=' + $home_ + '"'),
  ('set "USERPROFILE=' + $home_ + '"'),
  'set "UE_MCP_CONTEXT_STRATEGY=micro"',
  ('set "UE_MCP_BRIDGE_TOKEN_DIR=' + $TokenDir + '"'),
  ('cd /d "' + $projectDir + '"'),
  ($node + ' "' + $WrapperPath + '" -- ' + $node + ' "' + $npxCli + '" -y ue-mcp@' + $Version + ' "' + $UProject + '"')
) | Set-Content -Path $launcher -Encoding ascii
icacls $launcher /grant 'uemcp:RX' | Out-Null

"command=`"$launcher`",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty $PublicKey" | Set-Content $authorizedKeys -Encoding ascii
# StrictModes accepts only an owner of the user, BUILTIN\Administrators or SYSTEM (an individual admin's file is silently rejected).
icacls $authorizedKeys /setowner 'BUILTIN\Administrators' | Out-Null
icacls $authorizedKeys /inheritance:r | Out-Null
icacls $authorizedKeys /grant:r 'uemcp:R' 'SYSTEM:F' 'Administrators:F' | Out-Null
icacls $authorizedKeys
Write-Host ('Done. Now make the EDITOR use the same token folder, then restart it:  setx UE_MCP_BRIDGE_TOKEN_DIR "' + $TokenDir + '"  (as ' + $EditorUser + '; setx affects newly started programs only, so close the editor and start it again from a new shell/launcher). Then test from the lab per README.md.') -ForegroundColor Green
