[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RequestPath)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'LocalProvider-Ops.ps1')
# Determine a safe status destination before parsing incomplete JSON.
$requestFile = [IO.Path]::GetFullPath($RequestPath)
$directory = Split-Path -Parent $requestFile
$runName = Split-Path -Leaf $directory
if ($runName -notmatch '^[A-Za-z0-9_-]+$' -or $requestFile -ne (Join-Path $root ('.runtime\detached\'+$runName+'\request.json'))) { throw 'Detached request path does not match a repository run.' }
if (-not (Test-Path -LiteralPath $directory -PathType Container)) { throw 'Detached request directory missing.' }
if (Test-Path -LiteralPath (Join-Path $directory 'status.json')) { throw 'Detached request already completed; refusing replay.' }
$stage = 'configuration'; $exitCode = 1
try {
    $request = Get-Content -Raw -LiteralPath $requestFile | ConvertFrom-Json
    if ($request.runName -cne $runName -or $request.provider -notin @('ollama','claude') -or $request.protectedTwitch -isnot [bool] -or $null -eq $request.environment) { throw 'Invalid detached launch request.' }
    $launcher = Join-Path $PSScriptRoot 'Start-Local.ps1'
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw 'Normal launcher missing.' }
    $allowed = @(Get-DetachedLocalEnvironmentNames)
    foreach ($property in $request.environment.PSObject.Properties) {
        if ($property.Name -notin $allowed -or ($null -ne $property.Value -and $property.Value -isnot [string])) { throw 'Unsupported detached environment setting.' }
    }
    foreach ($key in $allowed) { [Environment]::SetEnvironmentVariable($key,$request.environment.$key,'Process') }
    # Never rely on secrets inherited from the WMI host. Read DPAPI only here.
    foreach ($key in @('TWITCH_CLIENT_ID','TWITCH_CLIENT_SECRET','ANTHROPIC_API_KEY','APP_GATEWAY_SECRET')) {
        [Environment]::SetEnvironmentVariable($key,$null,'Process')
    }
    $launch = {
        & $launcher -LaunchName $request.runName -Provider $request.provider 1> (Join-Path $directory 'launcher.stdout.log') 2> (Join-Path $directory 'launcher.stderr.log')
    }
    $stage = 'normal_launcher'
    if ($request.protectedTwitch) { Invoke-WithLocalTwitchCredentials -AppRoot $root -Action $launch }
    else { & $launch }
    $exitCode = 0; $stage = 'ready'
} catch {
    if ($_.Exception.Message -eq 'Protected Twitch configuration could not be loaded for this Windows account.') { $stage='protected_twitch' }
    $_.Exception.Message | Out-File -LiteralPath (Join-Path $directory 'launcher.stderr.log') -Append -Encoding utf8
} finally {
    $env:TWITCH_CLIENT_ID = $null; $env:TWITCH_CLIENT_SECRET = $null
    @{exitCode=$exitCode;stage=$stage;completedUtc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $directory 'status.pending.json') -Encoding utf8
    Move-Item -LiteralPath (Join-Path $directory 'status.pending.json') -Destination (Join-Path $directory 'status.json')
}
exit $exitCode
