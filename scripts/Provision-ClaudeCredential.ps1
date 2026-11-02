[CmdletBinding()]param([switch]$Execute)
$ErrorActionPreference='Stop'
if (-not $Execute) {Write-Output 'NOOP: no credential requested or written.';return}
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dir=$root
foreach($part in @('.runtime','mesa04','credentials')) {
    $dir=Join-Path $dir $part
    if (-not (Test-Path -LiteralPath $dir)) {New-Item -ItemType Directory -Path $dir | Out-Null}
    $item=Get-Item -LiteralPath $dir -Force
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {throw 'Credential directory must be a real directory under the app.'}
}
$path=Join-Path $dir 'anthropic.dpapi'
if (Test-Path -LiteralPath $path) {throw 'Credential already exists; refusing overwrite.'}
$secure=Read-Host 'Claude API credential (input hidden; bound to this Windows account)' -AsSecureString
try {
 if (-not $secure -or $secure.Length -eq 0) {throw 'Empty credential; nothing written.'}
 $encrypted=ConvertFrom-SecureString -SecureString $secure
 $stream=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
 try {$bytes=[Text.Encoding]::UTF8.GetBytes($encrypted);$stream.Write($bytes,0,$bytes.Length);$stream.Flush()} finally {$stream.Dispose()}
 Write-Output 'Encrypted credential provisioned for the current Windows account.'
} finally {if($secure){$secure.Dispose()};$encrypted=$null;$bytes=$null}