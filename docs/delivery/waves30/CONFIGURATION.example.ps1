# Review before dot-sourcing. No secrets; no dotenv loader.
$env:APP_HOST = '127.0.0.1'
$env:APP_PORT = '18765'
$env:APP_DATA_DIR = (Join-Path (Get-Location) 'data')
$env:APP_CLIENT_DIR = (Join-Path (Get-Location) 'client')
$env:APP_AI_PROVIDER = 'ollama'
$env:OLLAMA_URL = 'http://127.0.0.1:11434'
$env:OLLAMA_MODEL = 'qwen3.5:9b'
# Optional ASR needs separately installed pinned dependencies and local assets.
# No hosted-profile flag, credential, observation peer or operator paths here.
