[CmdletBinding()]
param([switch]$Foreground, [ValidateSet('ollama','claude')][string]$Provider, [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$LaunchName, [hashtable]$LaunchState,
    [switch]$Detached, [string]$PowerShellPath, [switch]$ProtectedTwitch)

$ErrorActionPreference = 'Stop'
$ChosenProvider = if ($Provider) { $Provider } elseif ($env:APP_AI_PROVIDER) { $env:APP_AI_PROVIDER } else { 'ollama' }
if ($ChosenProvider -notin @('ollama','claude')) { throw 'Invalid provider.' }
$AppRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'LocalProvider-Ops.ps1')
if ($Detached) {
    if ($Foreground -or $LaunchState) { throw '-Detached cannot be combined with -Foreground or -LaunchState.' }
    Start-DetachedLocal -AppRoot $AppRoot -Provider $ChosenProvider -LaunchName $LaunchName -PowerShellPath $PowerShellPath -ProtectedTwitch:$ProtectedTwitch
    return
}
if ($PowerShellPath -or $ProtectedTwitch) { throw '-PowerShellPath and -ProtectedTwitch require -Detached.' }
if ($null -eq $LaunchState) { $LaunchState=@{} }; $LaunchState.phase='before'
function Test-LocalHttpReady([string]$BaseUrl) {
    try { return (Invoke-WebRequest -Uri "$BaseUrl/" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 }
    catch { return $false }
}
function Get-AppListenerOwners([int]$ListenPort) {
    $owners = @(Get-ListenerOwners $ListenPort)
    foreach ($owner in $owners) {
        try { $details = Get-CimInstance Win32_Process -Filter "ProcessId = $owner" -ErrorAction Stop }
        catch { throw "Cannot verify listener PID $owner command line via CIM. No process was started." }
        if (-not $details) { throw "Listener PID $owner disappeared during verification. No process was started." }
    }
    return $owners
}
$Original = @{}
foreach ($Name in @('APP_HOST','APP_PORT','APP_DATA_DIR','OLLAMA_MODEL','ASR_PYTHON','ASR_MODEL_PATH','ASR_LANGUAGE')) {
    $Original[$Name] = [Environment]::GetEnvironmentVariable($Name,'Process')
}
try {
$Python = (Get-Command python -ErrorAction Stop).Source
$PythonVersion = (& $Python --version 2>&1 | Out-String).Trim()
if ($PythonVersion -notmatch '^Python 3\.12\.') { throw "Python 3.12 is required; found $PythonVersion." }
if (-not (Test-Path -LiteralPath (Join-Path $AppRoot 'server\__main__.py'))) { throw 'Backend files are missing.' }

$BindHost = if ($env:APP_HOST) { $env:APP_HOST.Trim() } else { '127.0.0.1' }
if ($BindHost -ne '127.0.0.1') { throw 'APP_HOST must be 127.0.0.1; server.ThreadingHTTPServer is IPv4-only.' }
$Port = 8765
if ($env:APP_PORT) {
    $parsedPort = 0
    if (-not [int]::TryParse($env:APP_PORT,[ref]$parsedPort) -or $parsedPort -lt 1 -or $parsedPort -gt 65535) { throw 'APP_PORT must be an integer from 1 through 65535.' }
    $Port = $parsedPort
}
$DataDir = if ($env:APP_DATA_DIR) { if ([IO.Path]::IsPathRooted($env:APP_DATA_DIR)) { [IO.Path]::GetFullPath($env:APP_DATA_DIR) } else { [IO.Path]::GetFullPath((Join-Path $AppRoot $env:APP_DATA_DIR)) } } else { Join-Path $AppRoot 'data' }
$DataPrefix = $AppRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not $DataDir.StartsWith($DataPrefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'APP_DATA_DIR must remain inside this repository.' }

$AsrPython = Join-Path $AppRoot '.venv-asr\Scripts\python.exe'
$AsrRoot = Join-Path $AppRoot '.runtime\huggingface\hub\models--Systran--faster-whisper-small\snapshots\536b0662742c02347bc0e980a01041f333bce120'
$RequiredModelFiles = @('model.bin','config.json','tokenizer.json')
$DefaultVocabulary = (Test-Path -LiteralPath (Join-Path $AsrRoot 'vocabulary.txt')) -or (Test-Path -LiteralPath (Join-Path $AsrRoot 'vocabulary.json'))
$DefaultAsrValid = (Test-Path -LiteralPath $AsrPython) -and $DefaultVocabulary -and (@($RequiredModelFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $AsrRoot $_)) }).Count -eq 0)
$ExplicitAsr = [bool]($env:ASR_PYTHON -or $env:ASR_MODEL_PATH)
if (-not $ExplicitAsr -and $DefaultAsrValid) {
    $env:ASR_PYTHON = $AsrPython
    $env:ASR_MODEL_PATH = $AsrRoot
    if (-not $env:ASR_LANGUAGE) { $env:ASR_LANGUAGE = 'en' }
} elseif ($ExplicitAsr) {
    $ModelPath = $env:ASR_MODEL_PATH
    $HasVocabulary = $ModelPath -and ((Test-Path -LiteralPath (Join-Path $ModelPath 'vocabulary.txt')) -or (Test-Path -LiteralPath (Join-Path $ModelPath 'vocabulary.json')))
    $HasModelFiles = $ModelPath -and (@($RequiredModelFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $ModelPath $_)) }).Count -eq 0)
    $ExplicitAsrValid = $env:ASR_PYTHON -and (Test-Path -LiteralPath $env:ASR_PYTHON) -and $HasVocabulary -and $HasModelFiles
    if (-not $ExplicitAsrValid) { Write-Warning 'Explicit ASR settings are incomplete or unavailable; they are preserved and health will report engine status.' }
}
if (-not $env:OLLAMA_MODEL) { $env:OLLAMA_MODEL = 'qwen3.5:9b' }
$env:APP_HOST = $BindHost
$env:APP_PORT = [string]$Port
$env:APP_DATA_DIR = $DataDir
$ChosenModel = if ($ChosenProvider -eq 'claude') { 'claude-sonnet-5-5' } else { $env:OLLAMA_MODEL }
$AsrConfig = @{python=$env:ASR_PYTHON;modelPath=$env:ASR_MODEL_PATH;language=$env:ASR_LANGUAGE}

$Bound = @(Get-AppListenerOwners $Port)
if ($Bound.Count -gt 0) {
    $owners = $Bound -join ','
    throw "Port $Port is already listening (PID $owners); no process was started."
}

# An exclusive bind probe catches occupied endpoints even when LISTEN enumeration misses them.
$PortProbe = [Net.Sockets.Socket]::new([Net.Sockets.AddressFamily]::InterNetwork,[Net.Sockets.SocketType]::Stream,[Net.Sockets.ProtocolType]::Tcp)
try {
    $PortProbe.ExclusiveAddressUse=$true
    $PortProbe.Bind([Net.IPEndPoint]::new([Net.IPAddress]::Parse('127.0.0.1'),$Port))
} catch { throw "Port $Port cannot be exclusively bound; no process was started." }
finally { $PortProbe.Dispose() }

$RunName = if ($LaunchName) { $LaunchName } else { 'M02-LOCAL-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6) }
$RunDir = Join-Path $AppRoot ('.runtime\run\' + $RunName)
if (Test-Path -LiteralPath $RunDir) { throw 'Launch run already exists.' }
New-Item -ItemType Directory -Path $RunDir | Out-Null
$Stdout = Join-Path $RunDir 'server.stdout.log'
$Stderr = Join-Path $RunDir 'server.stderr.log'
$BaseUrl = "http://${BindHost}:$Port"
$LaunchState | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $RunDir 'launch-state.json')
$key=$null;$childEnv=$null
try {
    if ($ChosenProvider -eq 'claude') { $key=Read-LocalClaudeKey (Join-Path $AppRoot '.runtime\mesa04\credentials\anthropic.dpapi') }
    $childEnv=@{APP_AI_PROVIDER=$ChosenProvider;ANTHROPIC_API_KEY=$key;APP_CLAUDE_LEDGER=$null;APP_CLAUDE_CAP_USD=$null;APP_CLAUDE_MAX_CALLS=$null}
    if ($ChosenProvider -eq 'claude') {
        $childEnv.APP_CLAUDE_LEDGER=Join-Path $AppRoot '.runtime\mesa02\claude-ledger.jsonl'
        $childEnv.APP_CLAUDE_CAP_USD='0.50';$childEnv.APP_CLAUDE_MAX_CALLS='24'
    }
    $Process=Start-ScopedBackend $Python $AppRoot $Stdout $Stderr $childEnv $LaunchState ([bool]$Foreground)
    $LaunchState | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $RunDir 'launch-state.json')
} finally { if ($childEnv) { $childEnv.ANTHROPIC_API_KEY=$null }; $key=$null }

$Child = Get-Process -Id $Process.Id -ErrorAction Stop
$CodeHashes=@{}
Get-ChildItem -LiteralPath (Join-Path $AppRoot 'server') -Filter '*.py' -File | ForEach-Object {
    $stream=[IO.File]::OpenRead($_.FullName)
    $sha=[Security.Cryptography.SHA256]::Create()
    try { $CodeHashes[$_.Name]=([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose(); $stream.Dispose() }
}
$ManifestPath = Join-Path $RunDir 'launch.json'
$Manifest = [ordered]@{runName=$RunName;listenerPid=$Process.Id;python=$Python;pythonVersion=$PythonVersion;command='python -m server';workingDirectory=$AppRoot;host=$BindHost;port=$Port;database=$DataDir;model=$ChosenModel;provider=$ChosenProvider;providerAvailable=$null;providerTested=$false;healthSha256=$null;ledger=if ($ChosenProvider -eq 'claude') { '.runtime/mesa02/claude-ledger.jsonl' } else { $null };capUsd=if ($ChosenProvider -eq 'claude') { 0.50 } else { $null };maxCalls=if ($ChosenProvider -eq 'claude') { 24 } else { $null };asr=$AsrConfig;codeSha256=$CodeHashes;httpReady=$false;healthOk=$false;startedAtUtc=$Child.StartTime.ToUniversalTime().ToString('o')}
$Manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $ManifestPath
$Ready=$false
for ($Attempt=0;$Attempt -lt 20;$Attempt++) {
    Start-Sleep -Milliseconds 500
    if (-not (Get-Process -Id $Process.Id -ErrorAction SilentlyContinue)) {break}
    $probeText=& (Join-Path $AppRoot 'scripts/Readiness-Local.ps1') -RunName $RunName
    $Probe=$probeText | ConvertFrom-Json
    if ($Probe.observation -and ($Probe.observation.root.ownershipStatus -like 'conflicting_*' -or $Probe.observation.healthRequest.ownershipStatus -like 'conflicting_*')) {throw 'Conflicting TCP ownership; no process was stopped.'}
    if ($Probe.httpReady -and $Probe.healthOk -and $Probe.processIdentityVerified -and $Probe.ownershipVerified) {$Ready=$true;break}
}
if (-not $Ready) {throw "Child PID $($Process.Id) did not pass independent HTTP, identity and ownership readiness; no process was stopped. Inspect $RunDir."}
$Probe | ConvertTo-Json -Depth 15 | Set-Content -Encoding utf8 (Join-Path $RunDir 'readiness.json')
$Health=$Probe.observation.health
$Ai=$Health.provider
$Asr=$Health.asr
$Manifest.database=$DataDir
$healthBytes=[Text.Encoding]::UTF8.GetBytes(($Health | ConvertTo-Json -Depth 20 -Compress))
$hasher=[Security.Cryptography.SHA256]::Create()
try { $Manifest.healthSha256=([BitConverter]::ToString($hasher.ComputeHash($healthBytes))).Replace('-','').ToLowerInvariant() } finally { $hasher.Dispose() }
$Manifest.model=$Ai.model;$Manifest.providerAvailable=$Ai.available;$Manifest.providerTested=$Ai.tested;$Manifest.asrConfigured=$Asr.configured;$Manifest.asrAvailable=$Asr.available;$Manifest.httpReady=$true;$Manifest.healthOk=$true
$Manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $ManifestPath
Write-Output "http-ready pid=$($Process.Id) url=$BaseUrl provider=$ChosenProvider model=$($Ai.model) available=$($Ai.available) asrConfigured=$($Asr.configured) asrAvailable=$($Asr.available) run=$RunDir manifest=$ManifestPath"
if ($Foreground) { Wait-Process -Id $Process.Id }

} finally { foreach ($Name in $Original.Keys) { [Environment]::SetEnvironmentVariable($Name,$Original[$Name],'Process') } }
