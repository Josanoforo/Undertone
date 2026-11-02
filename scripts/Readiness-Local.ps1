[CmdletBinding()]
param([Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9_-]+$')][string]$RunName)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$result=[ordered]@{runName=$RunName;httpReady=$false;healthOk=$false;processIdentityVerified=$false;ownershipVerified=$false;ownershipMethod=$null;cwdEvidence='launch manifest only; not independently observed';diskHashesEvidence='not inspected as loaded memory';observation=$null;error=$null}
function Confirm-ReadinessIdentity($m) {
 $pidExpected=[int]$m.listenerPid
 $p=Get-Process -Id $pidExpected -ErrorAction Stop
 $start=if($m.startedAtUtc -is [DateTime]){$m.startedAtUtc.ToUniversalTime()}else{([DateTimeOffset]::Parse([string]$m.startedAtUtc)).UtcDateTime}
 if ([IO.Path]::GetFullPath($p.Path) -ne [IO.Path]::GetFullPath([string]$m.python) -or [Math]::Abs(($p.StartTime.ToUniversalTime()-$start).TotalSeconds) -gt 2) {throw 'Process executable or start mismatch.'}
 $c=Get-CimInstance Win32_Process -Filter "ProcessId = $pidExpected" -ErrorAction Stop
 $exe=[regex]::Escape([string]$m.python)
 if (-not $c -or [IO.Path]::GetFullPath($c.ExecutablePath) -ne [IO.Path]::GetFullPath([string]$m.python) -or $c.CommandLine -notmatch ('^(?:"'+$exe+'"|'+$exe+')\s+-m\s+server\s*$')) {throw 'Process command mismatch.'}
}
try {
 $base=(Resolve-Path (Join-Path $root '.runtime/run')).Path
 $run=(Resolve-Path -LiteralPath (Join-Path $base $RunName)).Path
 if (-not $run.StartsWith($base.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) {throw 'Invalid run path.'}
 $m=Get-Content -Raw -LiteralPath (Join-Path $run 'launch.json') | ConvertFrom-Json
 if ($m.runName -ne $RunName -or $m.workingDirectory -ne $root -or $m.host -ne '127.0.0.1' -or $m.command -ne 'python -m server' -or $m.provider -notin @('claude','ollama') -or [int]$m.listenerPid -le 0 -or [int]$m.port -lt 1 -or [int]$m.port -gt 65535) {throw 'Manifest identity mismatch.'}
 Confirm-ReadinessIdentity $m
 $result.pid=[int]$m.listenerPid;$result.port=[int]$m.port;$result.startedAtUtc=$m.startedAtUtc
 $text=& $m.python (Join-Path $PSScriptRoot 'local_readiness_probe.py') ([string]$m.port) ([string]$m.listenerPid) ([string]$m.provider)
 if ($LASTEXITCODE -ne 0) {throw 'Readiness probe failed.'}
 $observation=($text | Out-String | ConvertFrom-Json)
 $result.observation=$observation
 $result.httpReady=[bool]$observation.httpReady
 $result.healthOk=[bool]$observation.healthOk
 $result.ownershipVerified=[bool]$observation.ownershipVerified
 $result.ownershipMethod=$observation.ownershipMethod
 Confirm-ReadinessIdentity $m
 $result.processIdentityVerified=$true
 if ($observation.health -and $observation.health.provider.model -ne $m.model) {$result.healthOk=$false;$result.error='Health model differs from launch manifest.'}
} catch {
 $result.error=$_.Exception.Message
 $result.processIdentityVerified=$false
 $result.ownershipVerified=$false
 $result.ownershipMethod=$null
}
$result | ConvertTo-Json -Depth 15 -Compress