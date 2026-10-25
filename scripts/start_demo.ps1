[CmdletBinding()]
param(
    [switch]$Live,
    [int]$Port = 8135,
    [string]$HostAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

if ($Live) {
    $env:REPLAY = "0"
    Write-Host "Starting in LIVE mode (REPLAY=0)" -ForegroundColor Cyan
} else {
    $env:REPLAY = "1"
    Write-Host "Starting in REPLAY mode (REPLAY=1)" -ForegroundColor Cyan
}

$listener = $null
try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse($HostAddress), $Port)
    $listener.Start()
    $listener.Stop()
} catch {
    Write-Error "Port $Port is already in use on $HostAddress. Please free the port or choose another port."
    exit 1
}

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RootDir

Write-Host "Starting AgentGuard FastAPI application on $HostAddress`:$Port..."
$proc = Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "app.main:app", "--host", $HostAddress, "--port", $Port -PassThru -NoNewWindow

$healthUrl = "http://${HostAddress}:${Port}/health"
$maxAttempts = 40
$attempt = 0
$healthy = $false

Write-Host "Waiting for application to become ready..." -NoNewline
while ($attempt -lt $maxAttempts) {
    Start-Sleep -Milliseconds 500
    Write-Host "." -NoNewline
    try {
        $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) {
            $healthy = $true
            break
        }
    } catch {
        # continue polling
    }
    $attempt++
}
Write-Host ""

if (-not $healthy) {
    Write-Error "Application failed to respond at $healthUrl within timeout."
    if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
    exit 1
}

Write-Host "`n=======================================================" -ForegroundColor Green
Write-Host " AgentGuard Demo is running!" -ForegroundColor Green
Write-Host " Food Demo Panel: http://${HostAddress}:${Port}/food-demo/" -ForegroundColor Yellow
Write-Host " FoodHub Site:    http://${HostAddress}:${Port}/foodhub/" -ForegroundColor Yellow
Write-Host " QuickBite Site:  http://${HostAddress}:${Port}/quickbite/" -ForegroundColor Yellow
Write-Host " DineDash Site:   http://${HostAddress}:${Port}/dinedash/" -ForegroundColor Yellow
Write-Host " Process ID:      $($proc.Id)"
Write-Host " Press Ctrl+C or kill process $($proc.Id) to stop."
Write-Host "=======================================================`n" -ForegroundColor Green

try {
    $proc.WaitForExit()
} finally {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}
