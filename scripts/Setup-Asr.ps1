$ErrorActionPreference = 'Stop'
$AppRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Runtime = Join-Path $AppRoot '.runtime'
$Temp = Join-Path $Runtime 'tmp\asr-setup'
$Cache = Join-Path $Runtime 'pip\cache'
$Previous = @{}
foreach ($Name in @('TEMP','TMP','TMPDIR','PIP_CACHE_DIR','HF_HOME','HF_HUB_DISABLE_IMPLICIT_TOKEN','HF_HUB_DISABLE_TELEMETRY')) { $Previous[$Name] = [Environment]::GetEnvironmentVariable($Name,'Process') }
New-Item -ItemType Directory -Force -Path $Temp,$Cache,(Join-Path $Runtime 'huggingface') | Out-Null
$env:TEMP = $Temp; $env:TMP = $Temp; $env:TMPDIR = $Temp
$env:PIP_CACHE_DIR = $Cache; $env:HF_HOME = Join-Path $Runtime 'huggingface'
$env:HF_HUB_DISABLE_IMPLICIT_TOKEN = '1'; $env:HF_HUB_DISABLE_TELEMETRY = '1'
$Python = Join-Path $AppRoot '.venv-asr\Scripts\python.exe'
try {
    if (-not (Test-Path -LiteralPath $Python)) { python -m venv (Join-Path $AppRoot '.venv-asr') }
    if (-not (Test-Path -LiteralPath $Python)) { throw 'Python could not create app/.venv-asr.' }
    & $Python -m pip install --disable-pip-version-check --requirement (Join-Path $PSScriptRoot 'ASR_REQUIREMENTS_LOCK.txt')
    if ($LASTEXITCODE -ne 0) { throw 'ASR dependency installation failed.' }
    & $Python (Join-Path $PSScriptRoot 'Download-AsrModel.py')
    if ($LASTEXITCODE -ne 0) { throw 'Pinned ASR model download or hash verification failed.' }
    Write-Host "Set ASR_PYTHON=$Python"
    Write-Host 'Set ASR_MODEL_PATH to the verified path printed above.'
} finally {
    foreach ($Name in $Previous.Keys) { [Environment]::SetEnvironmentVariable($Name,$Previous[$Name],'Process') }
}

