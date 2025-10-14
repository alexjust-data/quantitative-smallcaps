# Monitor intraday event detection progress
# Usage: powershell -File monitor.ps1

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "INTRADAY EVENT DETECTION MONITOR" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Find latest log
$latestLog = Get-ChildItem "D:\04_TRADING_SMALLCAPS\logs\detect_events\run_full_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if (-not $latestLog) {
    Write-Host "No log file found!" -ForegroundColor Red
    exit 1
}

Write-Host "Log file: $($latestLog.Name)" -ForegroundColor Green
Write-Host "Size: $([math]::Round($latestLog.Length/1KB, 2)) KB | Lines: $(Get-Content $latestLog.FullName | Measure-Object -Line).Lines"
Write-Host ""

# Check if process is running
$process = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*detect_events_intraday*" }
if ($process) {
    Write-Host "Status: RUNNING" -ForegroundColor Green -NoNewline
    Write-Host " (PID: $($process.Id))"
} else {
    Write-Host "Status: NOT RUNNING" -ForegroundColor Red
}
Write-Host ""

# Show last 10 lines (without color codes)
Write-Host "Last 10 log entries:" -ForegroundColor Yellow
Write-Host "----------------------------------------"
Get-Content $latestLog.FullName -Tail 10 | ForEach-Object { $_ -replace '\x1b\[[0-9;]*m', '' }
Write-Host ""

# Check checkpoint
$checkpoint = Get-ChildItem "D:\04_TRADING_SMALLCAPS\logs\checkpoints\events_intraday_*_completed.json" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($checkpoint) {
    $cpData = Get-Content $checkpoint.FullName | ConvertFrom-Json
    Write-Host "Checkpoint:" -ForegroundColor Yellow
    Write-Host "  Completed symbols: $($cpData.total_completed)"
    Write-Host "  Last updated: $($cpData.last_updated)"
    Write-Host ""
}

# Count shards
$shards = Get-ChildItem "D:\04_TRADING_SMALLCAPS\processed\events\shards\events_intraday_*_shard*.parquet" -ErrorAction SilentlyContinue
Write-Host "Shards saved: $($shards.Count)" -ForegroundColor Yellow
if ($shards) {
    $totalSize = ($shards | Measure-Object -Property Length -Sum).Sum
    Write-Host "Total size: $([math]::Round($totalSize/1MB, 2)) MB" -ForegroundColor Yellow
}
Write-Host ""

Write-Host "To watch live:" -ForegroundColor Cyan
Write-Host "  Get-Content '$($latestLog.FullName)' -Wait -Tail 20"
