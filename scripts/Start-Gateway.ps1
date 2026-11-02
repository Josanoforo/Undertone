[CmdletBinding()]
param([switch]$Execute)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = (Get-Command python -ErrorAction Stop).Source
$version = (& $python --version 2>&1 | Out-String).Trim()
if ($version -notmatch '^Python 3\.12\.') { throw 'Python 3.12 is required.' }
& $python -B (Join-Path $PSScriptRoot 'gateway_preflight.py')
if ($LASTEXITCODE -ne 0) { throw 'Gateway preflight failed.' }
if (-not $Execute) { Write-Output 'Preflight only; use -Execute after configuring the backend and trusted HTTPS ingress.'; exit 0 }
Push-Location $root
try { & $python -B -m server.gateway; if ($LASTEXITCODE -ne 0) { throw 'Gateway exited unsuccessfully.' } }
finally { Pop-Location }
