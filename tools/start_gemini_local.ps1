param([switch]$TemporaryExtra)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonExecutable = Join-Path $projectRoot '.venv/Scripts/python.exe'
$databaseFile = Join-Path $projectRoot 'interview.db'
if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) { throw 'Python .venv is missing.' }
if (-not (Test-Path -LiteralPath $databaseFile -PathType Leaf)) { throw 'Existing interview.db not found. Stop and check the database location.' }

$probe = [System.Net.Sockets.TcpClient]::new()
try {
    $pendingConnection = $probe.BeginConnect('127.0.0.1', 8000, $null, $null)
    if ($pendingConnection.AsyncWaitHandle.WaitOne(1000) -and $probe.Connected) {
        throw 'Port 8000 is in use. Stop the existing local server before running this script.'
    }
} finally { $probe.Dispose() }

$names = @('DATABASE_URL','COOKIE_SECURE','AI_PROVIDER','AI_PROVIDER_KEY','AI_MODEL_ID','AI_ALLOWED_MODEL_IDS',
    'AI_LIVE_ENABLED','PAID_AI_ENABLED','AI_MAX_COST_MICROUSD','AI_MAX_OUTPUT_TOKENS','AI_MAX_CALLS_PER_RUN',
    'AI_INPUT_RATE_MICROUSD_PER_MILLION_TOKENS','AI_OUTPUT_RATE_MICROUSD_PER_MILLION_TOKENS')
$old = @{}
foreach ($name in $names) { $old[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
Push-Location -LiteralPath $projectRoot
try {
    $secret = Read-Host 'Gemini API key (input is hidden)' -AsSecureString
    if ($secret.Length -eq 0) { throw 'No API key entered.' }
    $env:AI_PROVIDER_KEY = [System.Net.NetworkCredential]::new('', $secret).Password
    Remove-Variable secret
    $env:DATABASE_URL = 'sqlite:///./interview.db'
    $env:COOKIE_SECURE = 'false'
    $env:AI_PROVIDER = 'gemini'
    $env:AI_MODEL_ID = 'gemini-3.6-flash'
    $env:AI_ALLOWED_MODEL_IDS = 'gemini-3.6-flash'
    $env:AI_LIVE_ENABLED = 'true'
    $env:PAID_AI_ENABLED = 'true'
    $env:AI_MAX_COST_MICROUSD = '500000'
    $env:AI_MAX_CALLS_PER_RUN = '15'
    if ($TemporaryExtra) {
        $env:AI_MAX_COST_MICROUSD = '600000'
        $env:AI_MAX_CALLS_PER_RUN = '18'
        Write-Host 'Temporary limits: 18 reserved calls and $0.60 estimated cost per run.'
    }
    $env:AI_MAX_OUTPUT_TOKENS = '4096'
    # Conservative published 2027 rates: $1.50 / $7.50 per million tokens.
    $env:AI_INPUT_RATE_MICROUSD_PER_MILLION_TOKENS = '1500000'
    $env:AI_OUTPUT_RATE_MICROUSD_PER_MILLION_TOKENS = '7500000'
    Write-Host 'Server starting at http://127.0.0.1:8000 (Ctrl+C to stop).'
    Write-Host 'No AI request is made until a report analysis button is pressed.'
    & $pythonExecutable -B -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
    if ($LASTEXITCODE -ne 0) { throw 'Server failed to start; inspect the message above.' }
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $old[$name], 'Process') }
    Pop-Location
}
