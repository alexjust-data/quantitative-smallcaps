# ================================================================================
# STOP WATCHDOG - FASE 3.2
# ================================================================================
# Creates pause flag to gracefully stop watchdog
# Watchdog will detect flag and stop on next check cycle
# ================================================================================

$ErrorActionPreference = "Stop"

$ProjectRoot = "D:\04_TRADING_SMALLCAPS"
$PauseFlagFile = Join-Path $ProjectRoot "RUN_PAUSED.flag"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "STOPPING WATCHDOG - FASE 3.2" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Create pause flag
try {
    New-Item -ItemType File -Path $PauseFlagFile -Force | Out-Null
    Write-Host "[OK] Pause flag created: RUN_PAUSED.flag" -ForegroundColor Green
    Write-Host ""
    Write-Host "Watchdog will stop on next check cycle (within 2 minutes)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To verify watchdog stopped:" -ForegroundColor Cyan
    Write-Host "  Get-Content logs\watchdog_fase32.log -Tail 20" -ForegroundColor Gray
    Write-Host ""
    Write-Host "To restart watchdog:" -ForegroundColor Cyan
    Write-Host "  Remove-Item RUN_PAUSED.flag" -ForegroundColor Gray
    Write-Host "  powershell -ExecutionPolicy Bypass -File tools\fase_3.2\watchdog_start.ps1" -ForegroundColor Gray
    Write-Host ""
} catch {
    Write-Host "[ERROR] Failed to create pause flag: $_" -ForegroundColor Red
    exit 1
}

# Try to find and display watchdog jobs
$jobs = Get-Job | Where-Object { $_.Command -like "*watchdog_fase32*" }

if ($jobs) {
    Write-Host "Found $($jobs.Count) watchdog job(s):" -ForegroundColor White
    $jobs | ForEach-Object {
        Write-Host "  Job ID: $($_.Id) | State: $($_.State)" -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host "To force-stop jobs (if needed):" -ForegroundColor Yellow
    Write-Host "  Get-Job | Where-Object { `$_.Command -like '*watchdog_fase32*' } | Stop-Job" -ForegroundColor Gray
    Write-Host "  Get-Job | Where-Object { `$_.Command -like '*watchdog_fase32*' } | Remove-Job" -ForegroundColor Gray
}
