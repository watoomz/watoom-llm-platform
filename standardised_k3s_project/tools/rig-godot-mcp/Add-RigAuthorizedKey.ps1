<#
.SYNOPSIS
  Installs the lab's public key into godotmcp's authorized_keys, forced to run only the policy
  wrapper. Run after Setup-RigAccount.ps1 and after the lab playbook (godot-mcp-ssh.yml) has
  printed the key.
.DESCRIPTION
  Win32-OpenSSH needs tight ACLs on authorized_keys or it silently ignores the file, same as
  Linux sshd -- this sets them. Re-running replaces the file (so re-run if the lab's key changes,
  e.g. after deleting and re-generating /data/ai/godot-mcp-ssh/key on the lab).

  UNTESTED against the real editor/plugin/bridge -- see README.md's caveat.
.EXAMPLE
  .\Add-RigAuthorizedKey.ps1 -PublicKey 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5... watoom-godot-mcp' -ProjectPath F:\Documents\new-game-project
#>
[CmdletBinding()]
param(
  # Exact version of @npgamedev/godot-mcp-server (verified on the rig 2026-11-13); never run whatever npm publishes last.
  [string]$Version = '1.1.2',
  [Parameter(Mandatory)][string]$PublicKey,
  [string]$WrapperPath = 'C:\watoom\rig-godot-mcp\godot-mcp-policy-wrapper.js',
  # Absolute path: the restricted godotmcp account has no profile and a minimal PATH, so a bare `node` is not found.
  [string]$NodePath = (Get-Command node -ErrorAction SilentlyContinue).Source,
  # The open Godot project. The bridge reads the project path and the editor's token from the
  # environment, which the restricted account does not have, so the launcher sets both.
  [Parameter(Mandatory)][string]$ProjectPath,
  # The editor plugin's token FILE (per-project instance directory). If omitted, it is looked up under
  # C:\Users\*\AppData\Roaming\Godot\app_userdata\*\addons\godot_mcp_toolkit\*\mcp_token and used only
  # when exactly one exists. This script never reads or prints the token's contents.
  [string]$TokenPath
)
$ErrorActionPreference = 'Stop'
if (-not (Get-LocalUser -Name godotmcp -ErrorAction SilentlyContinue)) {
  throw 'godotmcp does not exist yet -- run Setup-RigAccount.ps1 first.'
}
if (-not $NodePath -or -not (Test-Path $NodePath)) {
  throw 'node.exe not found: install Node.js machine-wide, or pass -NodePath <full path to node.exe>.'
}
if ($PublicKey -notmatch '^ssh-') {
  throw "That doesn't look like a public key line (should start with ssh-ed25519/ssh-rsa/...). Paste exactly what the lab playbook printed."
}

# Not under the user's profile: godotmcp never logs on interactively, so it has no profile and sshd
# resolves its home to C:\Windows (it then looks for C:\Windows\.ssh\authorized_keys and fails with
# "Failed publickey"). Setup-RigAccount.ps1 points this account's AuthorizedKeysFile at this path.
$authorizedKeys = 'C:\ProgramData\ssh\godotmcp_authorized_keys'

if (-not (Test-Path -LiteralPath $ProjectPath)) { throw "ProjectPath not found: $ProjectPath" }
if (-not $TokenPath) {
  $found = @(Get-ChildItem 'C:\Users\*\AppData\Roaming\Godot\app_userdata\*\addons\godot_mcp_toolkit\*\mcp_token' -ErrorAction SilentlyContinue)
  if ($found.Count -ne 1) { throw "Found $($found.Count) mcp_token files; pass -TokenPath <full path to the editor's mcp_token>. (Open the project with the plugin enabled first.)" }
  $TokenPath = $found[0].FullName
}
if (-not (Test-Path -LiteralPath $TokenPath)) { throw "TokenPath not found: $TokenPath" }

# The key's forced command is a launcher, not "node wrapper.js" directly: sshd runs the command through
# cmd.exe, which mangles a command with several quoted parts ('""' is not recognized); the account has no
# profile and a minimal PATH (no node/npx); and spawn('npx') cannot start npx.cmd without a shell, so the
# bridge is started as `node npx-cli.js` instead. npm gets a cache directory the account can write.
$nodeDir = Split-Path $NodePath
$npxCli  = Join-Path $nodeDir 'node_modules\npm\bin\npx-cli.js'
if ($Version -notmatch '^\d+\.\d+\.\d+([-.][0-9A-Za-z.]+)?$') { throw '-Version must be an exact version like 1.1.2, not a range or a tag.' }
if (-not (Test-Path $npxCli)) { throw "npx-cli.js not found at $npxCli -- pass the node.exe of a standard Node.js install." }
$npmCache = 'C:\ProgramData\watoom\npm-cache'
New-Item -ItemType Directory -Force -Path $npmCache | Out-Null
icacls $npmCache /grant 'godotmcp:(OI)(CI)M' | Out-Null
$launcher = Join-Path (Split-Path $WrapperPath) 'run-godot-mcp.cmd'
$node = '"' + $NodePath + '"'
# Built from pieces and written as exactly these lines: a wrapped/split line becomes a separate batch command.
# The restricted account has no profile, so the bridge cannot find the editor's project or token on its own:
# the project path, the working directory and GODOT_MCP_TOKEN_PATH are set explicitly. GODOT_MCP_CONFIG_VERSION
# silences the bridge's "regenerate .mcp.json" warning.
@('@echo off',
  ('set "PATH=' + $nodeDir + ';%PATH%"'),
  ('set "npm_config_cache=' + $npmCache + '"'),
  ('set "GODOT_MCP_PROJECT_PATH=' + $ProjectPath + '"'),
  'cd /d "%GODOT_MCP_PROJECT_PATH%"',
  'set "GODOT_MCP_CONFIG_VERSION=1"',
  ('set "GODOT_MCP_TOKEN_PATH=' + $TokenPath + '"'),
  ($node + ' "' + $WrapperPath + '" -- ' + $node + ' "' + $npxCli + '" -y @npgamedev/godot-mcp-server@' + $Version)
) | Set-Content -Path $launcher -Encoding ascii
icacls $launcher /grant 'godotmcp:RX' | Out-Null
# Read access to the editor's token file only. Not a copy: the token stays where the editor writes it.
icacls $TokenPath /grant 'godotmcp:(R)' | Out-Null

"command=`"$launcher`",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty $PublicKey" `
    | Set-Content $authorizedKeys -Encoding ascii

# Win32-OpenSSH StrictModes only accepts an owner of the user, BUILTIN\Administrators or SYSTEM; a file
# created by an individual admin account is owned by that account and is silently rejected
# ("Failed publickey" with no other detail).
icacls $authorizedKeys /setowner 'BUILTIN\Administrators' | Out-Null
icacls $authorizedKeys /inheritance:r | Out-Null
icacls $authorizedKeys /grant:r 'godotmcp:R' 'SYSTEM:F' 'Administrators:F' | Out-Null
icacls $authorizedKeys

Write-Host 'Done. Test from the lab per README.md Install step 4.' -ForegroundColor Green
