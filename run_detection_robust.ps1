# Robust wrapper for intraday event detection with auto-restart
# This script automatically restarts the process if it crashes or is killed by Windows

param(
    [int]$MaxRestarts = 50,
    [int]$MaxMinutesPerRun = 30
)

$ErrorActionPreference = "Continue"
$ScriptDir = "D:\04_TRADING_SMALLCAPS"
$PythonScript = "scripts\processing\detect_events_intraday.py"
$SymbolFile = "processed\reference\symbols_with_1m.parquet"
$LogDir = "$ScriptDir\logs\detect_events"
$CheckpointFile = "$ScriptDir\logs\checkpoints\events_intraday_20251012_completed.json"

# Ensure we're in the correct directory
Set-Location $ScriptDir

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "ROBUST INTRADAY EVENT DETECTION - AUTO RESTART MODE" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "Script Directory: $ScriptDir" -ForegroundColor Green
Write-Host "Max Restarts: $MaxRestarts" -ForegroundColor Green
Write-Host "Max Minutes Per Run: $MaxMinutesPerRun" -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""

$restartCount = 0
$totalSymbolsProcessed = 0
$startTime = Get-Date

while ($restartCount -lt $MaxRestarts) {
    $runStartTime = Get-Date
    $runNumber = $restartCount + 1

    Write-Host ""
    Write-Host ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>" -ForegroundColor Yellow
    Write-Host "RUN #$runNumber - Starting at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
    Write-Host ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>" -ForegroundColor Yellow

    # Check checkpoint to see how many symbols completed
    if (Test-Path $CheckpointFile) {
        $checkpoint = Get-Content $CheckpointFile | ConvertFrom-Json
        $completed = $checkpoint.total_completed
        Write-Host "Checkpoint found: $completed symbols already completed" -ForegroundColor Green
        $totalSymbolsProcessed = $completed

        if ($completed -ge 1996) {
            Write-Host ""
            Write-Host "================================================================================" -ForegroundColor Green
            Write-Host "ALL SYMBOLS COMPLETED! ($completed/1996)" -ForegroundColor Green
            Write-Host "================================================================================" -ForegroundColor Green
            exit 0
        }
    } else {
        Write-Host "No checkpoint found - starting fresh" -ForegroundColor Cyan
    }

    # Create timeout job to kill process after MaxMinutesPerRun
    $timeoutSeconds = $MaxMinutesPerRun * 60

    # Start the Python process
    Write-Host "Launching Python process (timeout: $MaxMinutesPerRun minutes)..." -ForegroundColor Cyan

    $processStartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processStartInfo.FileName = "python"
    $processStartInfo.Arguments = "-u $PythonScript --from-file $SymbolFile --batch-size 50 --checkpoint-interval 1 --resume"
    $processStartInfo.WorkingDirectory = $ScriptDir
    $processStartInfo.UseShellExecute = $false
    $processStartInfo.RedirectStandardOutput = $false
    $processStartInfo.RedirectStandardError = $false
    $processStartInfo.CreateNoWindow = $false

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $processStartInfo

    try {
        $process.Start() | Out-Null
        $processId = $process.Id
        Write-Host "Process started with PID: $processId" -ForegroundColor Green

        # Wait for process to finish or timeout
        $finished = $process.WaitForExit($timeoutSeconds * 1000)

        if ($finished) {
            $exitCode = $process.ExitCode
            Write-Host ""
            Write-Host "Process finished with exit code: $exitCode" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Yellow" })

            if ($exitCode -eq 0) {
                Write-Host ""
                Write-Host "================================================================================" -ForegroundColor Green
                Write-Host "DETECTION COMPLETED SUCCESSFULLY!" -ForegroundColor Green
                Write-Host "================================================================================" -ForegroundColor Green
                exit 0
            }
        } else {
            Write-Host ""
            Write-Host "Process timeout after $MaxMinutesPerRun minutes - killing and restarting..." -ForegroundColor Yellow
            $process.Kill()
            Start-Sleep -Seconds 2
        }
    }
    catch {
        Write-Host "Error running process: $_" -ForegroundColor Red
    }
    finally {
        if ($process -and !$process.HasExited) {
            try {
                $process.Kill()
            }
            catch {}
        }
        $process.Dispose()
    }

    # Check progress after run
    $runEndTime = Get-Date
    $runDuration = ($runEndTime - $runStartTime).TotalMinutes

    if (Test-Path $CheckpointFile) {
        $checkpoint = Get-Content $CheckpointFile | ConvertFrom-Json
        $newCompleted = $checkpoint.total_completed
        $symbolsThisRun = $newCompleted - $totalSymbolsProcessed
        $totalSymbolsProcessed = $newCompleted

        Write-Host ""
        Write-Host "<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" -ForegroundColor Yellow
        Write-Host "RUN #$runNumber SUMMARY:" -ForegroundColor Yellow
        Write-Host "  Duration: $([math]::Round($runDuration, 2)) minutes" -ForegroundColor Yellow
        Write-Host "  Symbols processed this run: $symbolsThisRun" -ForegroundColor Yellow
        Write-Host "  Total symbols completed: $totalSymbolsProcessed / 1996" -ForegroundColor Yellow
        Write-Host "  Remaining: $(1996 - $totalSymbolsProcessed)" -ForegroundColor Yellow
        Write-Host "<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<" -ForegroundColor Yellow

        if ($symbolsThisRun -eq 0) {
            Write-Host ""
            Write-Host "WARNING: No progress made in this run - process may be stuck!" -ForegroundColor Red
            Write-Host "Waiting 10 seconds before retry..." -ForegroundColor Yellow
            Start-Sleep -Seconds 10
        }
    }

    $restartCount++

    Write-Host ""
    Write-Host "Restarting in 3 seconds... (restart $restartCount / $MaxRestarts)" -ForegroundColor Cyan
    Start-Sleep -Seconds 3
}

Write-Host ""
Write-Host "================================================================================" -ForegroundColor Red
Write-Host "MAX RESTARTS REACHED ($MaxRestarts)" -ForegroundColor Red
Write-Host "Total symbols processed: $totalSymbolsProcessed / 1996" -ForegroundColor Red
Write-Host "Total runtime: $([math]::Round(($(Get-Date) - $startTime).TotalMinutes, 2)) minutes" -ForegroundColor Red
Write-Host "================================================================================" -ForegroundColor Red
exit 1
