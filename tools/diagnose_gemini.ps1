param([switch]$MetadataOnly)
$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = Join-Path $root '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Python .venv is missing.' }
$names = @('AI_PROVIDER_KEY','AI_MODEL_ID','AI_ALLOWED_MODEL_IDS','AI_LIVE_ENABLED','PAID_AI_ENABLED','AI_MAX_COST_MICROUSD')
$old = @{}
foreach ($name in $names) { $old[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    $secret = Read-Host 'Gemini API key (input is hidden)' -AsSecureString
    if ($secret.Length -eq 0) { throw 'No API key entered.' }
    $env:AI_PROVIDER_KEY = [System.Net.NetworkCredential]::new('', $secret).Password
    Remove-Variable secret
    $env:AI_MODEL_ID = 'gemini-3.6-flash'
    $env:AI_ALLOWED_MODEL_IDS = 'gemini-3.6-flash'
    $env:AI_LIVE_ENABLED = 'true'
    $env:PAID_AI_ENABLED = 'true'
    $env:AI_MAX_COST_MICROUSD = '500000'
    if ($MetadataOnly) { & $python -B -X utf8 (Join-Path $PSScriptRoot 'diagnose_gemini.py') --metadata-only }
    else { & $python -B -X utf8 (Join-Path $PSScriptRoot 'diagnose_gemini.py') }
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $old[$name], 'Process') }
}
