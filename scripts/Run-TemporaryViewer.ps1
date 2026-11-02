[CmdletBinding()]
param([switch]$Execute, [switch]$Manual)
$ErrorActionPreference = 'Stop'
if (-not $Execute) { Write-Output 'Preflight only. Manual mode requires the coordinator release manifest; no tunnel was started.'; exit 0 }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = (Get-Command python -ErrorAction Stop).Source
if ($Manual) {
    $runtime = Join-Path $root '.runtime/mesa02/PHASE34-GATEWAY'
    $release = Join-Path $runtime 'MANUAL-RELEASE.json'
    if (-not (Test-Path -LiteralPath $release -PathType Leaf)) { throw 'The coordinator release manifest is missing; no process was started.' }
    $tag = [Guid]::NewGuid().ToString('N')
    $stdout = Join-Path $runtime "manual-host-$tag.out"
    $stderr = Join-Path $runtime "manual-host-$tag.err"
    $script = Join-Path $PSScriptRoot 'temporary_viewer_smoke.py'
    $proc = Start-Process -FilePath $python -ArgumentList @('-B', ('"' + $script + '"'), '--manual') -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    Write-Output "Manual host started with PID $($proc.Id); the private MANUAL-READY.json records API readiness; share the invitation with the human only after human-ready."
    exit 0
}
Push-Location $root
try { & $python -B (Join-Path $PSScriptRoot 'temporary_viewer_smoke.py'); exit $LASTEXITCODE }
finally { Pop-Location }
