# One command to start the backend (and the web app once web/ exists).
#   .\scripts\dev.ps1            real models (needs the GPU laptop; takes ~20 s to load)
#   .\scripts\dev.ps1 -Mock      canned results from mock/ and the stored demo targets, no GPU
#   .\scripts\dev.ps1 -Port 8001 -NoWeb
# Do not add --reload: it breaks the solver process pool on Windows.
param(
    [switch]$Mock,
    [switch]$NoWeb,
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $Mock) {
    python scripts/check_env.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`nFix the lines marked FAIL/MISSING/POINTER above, or run with -Mock." -ForegroundColor Yellow
        exit 1
    }
    Remove-Item Env:\MOCK -ErrorAction SilentlyContinue
} else {
    $env:MOCK = "1"
}

$web = Join-Path $root "web"
if (-not $NoWeb -and (Test-Path (Join-Path $web "package.json"))) {
    if (-not (Test-Path (Join-Path $web "node_modules"))) { Push-Location $web; npm install; Pop-Location }
    $env:VITE_API_URL = "http://127.0.0.1:$Port"
    Start-Process -FilePath "npm" -ArgumentList "run", "dev" -WorkingDirectory $web
    Write-Host "Web app: http://localhost:5173 (talks to http://127.0.0.1:$Port)" -ForegroundColor Green
} elseif (-not $NoWeb) {
    Write-Host "web/ does not exist yet; starting the API only." -ForegroundColor Yellow
}

Write-Host "API: http://127.0.0.1:$Port  (docs: /docs, health: /api/health)" -ForegroundColor Green
python -m uvicorn server.app:app --host 0.0.0.0 --port $Port
