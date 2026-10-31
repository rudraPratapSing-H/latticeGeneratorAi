# One command to start the backend AND the web app, and wait until the backend is ready.
#   .\scripts\dev.ps1                  real models (GPU laptop). Waits until /api/health says model_loaded (about 20 s).
#   .\scripts\dev.ps1 -Mock            no GPU: the backend replays stored real runs (mock/) and the stored demo targets (demo/)
#   .\scripts\dev.ps1 -WebMock         web app on its own client-side mock, no backend needed (rarely what you want)
#   .\scripts\dev.ps1 -NoWeb -Port 8001 -WebPort 5174
# Ctrl+C stops both. Logs: runs\dev\api.log, runs\dev\web.log. Do not add --reload: it breaks the solver pool on Windows.
param(
    [switch]$Mock,
    [switch]$WebMock,
    [switch]$NoWeb,
    [int]$Port = 8000,
    [int]$WebPort = 5173,
    [int]$TimeoutSec = 240
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$logs = Join-Path $root "runs\dev"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Fail($msg) { Write-Host "`n$msg" -ForegroundColor Red; exit 1 }

function Assert-PortFree([int]$p, [string]$what) {
    $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { Fail "Port $p ($what) is already in use by process $($c.OwningProcess). Stop it, or pick another port with -Port / -WebPort." }
}

function Stop-Tree($proc) {
    if ($proc -and -not $proc.HasExited) { & taskkill /PID $proc.Id /T /F | Out-Null }
}

# the web folder is called web/ in the plan; the teammate's checkout may still be lattice-web/
$webDir = $null
foreach ($name in @("web", "lattice-web")) {
    $d = Join-Path $root $name
    if (Test-Path (Join-Path $d "package.json")) { $webDir = $d; break }
}

if (-not $Mock) {
    python scripts/check_env.py
    if ($LASTEXITCODE -ne 0) { Fail "Fix the lines marked FAIL / MISSING / POINTER above, or run with -Mock." }
    Remove-Item Env:\MOCK -ErrorAction SilentlyContinue
} else {
    $env:MOCK = "1"
}

if (-not $WebMock) { Assert-PortFree $Port "API" }
if (-not $NoWeb -and $webDir) { Assert-PortFree $WebPort "web app" }

$api = $null; $web = $null
try {
    if (-not $WebMock) {
        $api = Start-Process -FilePath python -ArgumentList "-m", "uvicorn", "server.app:app", "--host", "127.0.0.1", "--port", "$Port" `
            -WorkingDirectory $root -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $logs "api.log") -RedirectStandardError (Join-Path $logs "api.err.log")
        Write-Host "Starting the API on http://127.0.0.1:$Port ..." -ForegroundColor Cyan
        $deadline = (Get-Date).AddSeconds($TimeoutSec)
        $ready = $false
        $reason = ""
        while ((Get-Date) -lt $deadline) {
            if ($api.HasExited) {
                Get-Content (Join-Path $logs "api.err.log") -Tail 15 -ErrorAction SilentlyContinue | Write-Host
                Fail "The API process exited (code $($api.ExitCode)). See runs\dev\api.err.log."
            }
            try {
                $h = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
                $reason = $h.reason
                if ($Mock -or $h.model_loaded) { $ready = $true; break }
                if ($reason -and $reason -notmatch "not loaded") {                    # loaded=false with a real reason: stop waiting
                    if ($h.model_loaded -eq $false -and $reason) { Write-Host "  waiting: $reason" -ForegroundColor DarkGray }
                }
            } catch { }
            Start-Sleep -Milliseconds 1000
        }
        if (-not $ready) { Fail "The API did not become ready in $TimeoutSec s. Health says: $reason`nSee runs\dev\api.err.log." }
        Write-Host "API ready (model_loaded: $($h.model_loaded), gpu: $($h.gpu), solver workers: $($h.solver_workers))" -ForegroundColor Green
    }

    if (-not $NoWeb) {
        if (-not $webDir) {
            Write-Host "No web folder (web/ or lattice-web/) found; API only." -ForegroundColor Yellow
        } else {
            if (-not (Test-Path (Join-Path $webDir "node_modules"))) {
                Write-Host "Installing web dependencies (npm ci) ..." -ForegroundColor Cyan
                Push-Location $webDir; npm ci; Pop-Location
            }
            $env:VITE_API_URL = "http://127.0.0.1:$Port"
            $env:VITE_USE_MOCK = $(if ($WebMock) { "true" } else { "false" })
            $web = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "npm run dev -- --host 127.0.0.1 --port $WebPort --strictPort" `
                -WorkingDirectory $webDir -PassThru -WindowStyle Hidden `
                -RedirectStandardOutput (Join-Path $logs "web.log") -RedirectStandardError (Join-Path $logs "web.err.log")
            $deadline = (Get-Date).AddSeconds(90)
            $up = $false
            while ((Get-Date) -lt $deadline) {
                try { Invoke-WebRequest -Uri "http://127.0.0.1:$WebPort/" -UseBasicParsing -TimeoutSec 3 | Out-Null; $up = $true; break } catch { }
                Start-Sleep -Milliseconds 700
            }
            if (-not $up) { Fail "The web app did not start in 90 s. See runs\dev\web.err.log." }
            Write-Host "Web app: http://127.0.0.1:$WebPort" -ForegroundColor Green
        }
    }

    Write-Host "`nReady. Ctrl+C stops everything.  API docs: http://127.0.0.1:$Port/docs" -ForegroundColor Green
    while ($true) {
        if ($api -and $api.HasExited) { Fail "The API process exited (code $($api.ExitCode)). See runs\dev\api.err.log." }
        Start-Sleep -Seconds 2
    }
} finally {
    Stop-Tree $web
    Stop-Tree $api
}
