# ================================================================================
# START WATCHDOG - FASE 3.2
# ================================================================================
# Launches watchdog in background to supervise Polygon ingestion
# ================================================================================

$ErrorActionPreference = "Stop"

$ProjectRoot = "D:\04_TRADING_SMALLCAPS"
$WatchdogScript = Join-Path $ProjectRoot "tools\fase_3.2\watchdog_fase32.ps1"
$PauseFlagFile = Join-Path $ProjectRoot "RUN_PAUSED.flag"

# Remove pause flag if exists
if (Test-Path $PauseFlagFile) {
    Write-Host "Removing pause flag..." -ForegroundColor Yellow
    Remove-Item $PauseFlagFile -Force
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "STARTING WATCHDOG - FASE 3.2" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if watchdog is already running
$existingWatchdog = Get-Process | Where-Object { $_.ProcessName -eq "powershell" -and $_.CommandLine -like "*watchdog_fase32.ps1*" }

if ($existingWatchdog) {
    Write-Host "[WARNING] Watchdog may already be running (PID: $($existingWatchdog.Id))" -ForegroundColor Yellow
    $response = Read-Host "Continue anyway? (y/n)"
    if ($response -ne "y") {
        Write-Host "Aborted." -ForegroundColor Red
        exit 1
    }
}

# Launch watchdog in background
try {
    $job = Start-Job -ScriptBlock {
        param($ScriptPath, $Root)
        Set-Location $Root
        & powershell -ExecutionPolicy Bypass -File $ScriptPath
    } -ArgumentList $WatchdogScript, $ProjectRoot

    Start-Sleep -Seconds 2

    $jobState = Get-Job -Id $job.Id | Select-Object -ExpandProperty State

    if ($jobState -eq "Running") {
        Write-Host "[OK] Watchdog started successfully" -ForegroundColor Green
        Write-Host ""
        Write-Host "Job ID: $($job.Id)" -ForegroundColor White
        Write-Host "Log file: logs\watchdog_fase32.log" -ForegroundColor White
        Write-Host ""
        Write-Host "To monitor:" -ForegroundColor Cyan
        Write-Host "  Get-Content logs\watchdog_fase32.log -Wait -Tail 50" -ForegroundColor Gray
        Write-Host ""
        Write-Host "To stop watchdog:" -ForegroundColor Cyan
        Write-Host "  powershell -ExecutionPolicy Bypass -File tools\fase_3.2\watchdog_stop.ps1" -ForegroundColor Gray
        Write-Host ""
    } else {
        Write-Host "[ERROR] Watchdog failed to start (State: $jobState)" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "[ERROR] Failed to start watchdog: $_" -ForegroundColor Red
    exit 1
}
