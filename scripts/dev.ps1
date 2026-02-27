param(
    [switch]$OnlyFrontend,
    [switch]$OnlyBackend
)

# PowerShell helper to start DB, backend and frontend in separate windows.
# Usage: `make dev` or: powershell -ExecutionPolicy Bypass -File scripts\dev.ps1

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# project root is parent of the scripts directory
$projectRoot = Resolve-Path (Join-Path $scriptDir '..')
$project = $projectRoot.ProviderPath
Set-Location -Path $project

if (-not $OnlyFrontend -and -not $OnlyBackend) {
    Write-Host 'Starting Postgres (docker compose)...'
    docker compose up -d | Out-Null
}

if (-not $OnlyFrontend) {
    Write-Host 'Starting backend in a new window...'
    $pythonPath = Join-Path $project '.venv\Scripts\python.exe'
    if (-not (Test-Path $pythonPath)) {
        Write-Host "Python executable not found at $pythonPath" -ForegroundColor Yellow
    }
    Start-Process -FilePath $pythonPath -ArgumentList 'app.py' -WorkingDirectory $project -WindowStyle Normal
}

if (-not $OnlyBackend) {
    Write-Host 'Starting frontend in a new window...'
    $frontendDir = Join-Path $project 'frontend'
    if (-not (Test-Path $frontendDir)) {
        Write-Host "Frontend directory not found at $frontendDir" -ForegroundColor Yellow
    }
    Start-Process -FilePath 'powershell' -ArgumentList "-NoProfile -ExecutionPolicy Bypass -Command `"cd '$frontendDir'; npm run dev`"" -WorkingDirectory $frontendDir -WindowStyle Normal
}

Start-Sleep -Seconds 1
Start-Process 'http://localhost:5173/'
Write-Host 'Launched UI (http://localhost:5173/) - check the opened terminal windows for logs.'