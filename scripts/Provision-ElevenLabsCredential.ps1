[CmdletBinding()]param([switch]$Execute)
$ErrorActionPreference='Stop'
if (-not $Execute) {Write-Output 'NOOP: no credential requested or written.';return}
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dir=$root
foreach($part in @('.runtime','credentials')) {
 $dir=Join-Path $dir $part
 if (-not (Test-Path -LiteralPath $dir)) {New-Item -ItemType Directory -Path $dir | Out-Null}
 $item=Get-Item -LiteralPath $dir -Force
 if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {throw 'Invalid credential directory'}
}
$path=Join-Path $dir 'elevenlabs-key.dpapi'
if (Test-Path -LiteralPath $path) {throw 'Refusing credential overwrite'}
Add-Type -AssemblyName System.Security
$secure=Read-Host 'ElevenLabs API credential (hidden, Windows account-bound)' -AsSecureString
$ptr=[IntPtr]::Zero
try {
 if (-not $secure -or $secure.Length -eq 0) {throw 'Empty credential'}
 $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
 $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
 if ($plain.Length -lt 8 -or $plain.Length -gt 512 -or $plain -match '[^\x21-\x7E]') {throw 'Invalid credential format'}
 $bytes=[Text.Encoding]::ASCII.GetBytes($plain)
 $encrypted=[Security.Cryptography.ProtectedData]::Protect($bytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
 $stream=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
 try {$stream.Write($encrypted,0,$encrypted.Length);$stream.Flush()} finally {$stream.Dispose()}
 Write-Output 'Credential provisioned; no provider call made.'
} finally {
 if($ptr -ne [IntPtr]::Zero){[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)}
 if($bytes){[Array]::Clear($bytes,0,$bytes.Length)}
 if($secure){$secure.Dispose()};$plain=$null;$encrypted=$null
}
