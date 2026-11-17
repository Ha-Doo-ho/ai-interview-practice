param([string]$DatabaseUrl = '')

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonExecutable = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
    throw 'Create .venv and install requirements.txt before starting the app.'
}
if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    $DatabaseUrl = 'sqlite:///./team-development.db'
}

$savedSettings = @{}
foreach ($setting in @('DATABASE_URL', 'AI_LIVE_ENABLED', 'PAID_AI_ENABLED', 'COOKIE_SECURE')) {
    $savedSettings[$setting] = [Environment]::GetEnvironmentVariable($setting, 'Process')
}
Push-Location -LiteralPath $projectRoot
try {
    $env:DATABASE_URL = $DatabaseUrl
    $env:AI_LIVE_ENABLED = 'false'
    $env:PAID_AI_ENABLED = 'false'
    $env:COOKIE_SECURE = 'false'
    Write-Host 'Starting local mock interview practice at http://127.0.0.1:8000 (Ctrl+C to stop).'
    & $pythonExecutable -B -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
    if ($LASTEXITCODE -ne 0) { throw 'Local app exited with an error. Inspect the server output.' }
}
finally {
    foreach ($setting in $savedSettings.Keys) {
        [Environment]::SetEnvironmentVariable($setting, $savedSettings[$setting], 'Process')
    }
    Pop-Location
}
