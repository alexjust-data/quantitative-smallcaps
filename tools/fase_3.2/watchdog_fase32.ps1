# ================================================================================
# WATCHDOG - FASE 3.2 POLYGON INGESTION
# ================================================================================
# Supervises Polygon ingestion process and relaunches if it crashes or stalls
# Uses checkpoint-based resume (idempotent - no duplicates)
# ================================================================================

param(
    [string]$Manifest = "processed\events\manifest_core_5y_20251017.parquet",
    [int]$RateLimit = 10,
    [int]$QuotesHz = 1,
    [int]$CheckIntervalSeconds = 120,  # Check every 2 minutes
    [int]$StallTimeoutSeconds = 300,   # Consider stalled if no log update in 5 minutes
    [int]$MaxRetries = 10,             # Max consecutive failures before giving up
    [int]$BackoffSeconds = 60          # Wait time after failure before retry
)

$ErrorActionPreference = "Continue"

# Paths
$ProjectRoot = "D:\04_TRADING_SMALLCAPS"
$PauseFlagFile = Join-Path $ProjectRoot "RUN_PAUSED.flag"
$WatchdogLog = Join-Path $ProjectRoot "logs\watchdog_fase32.log"

# Ensure log directory exists
New-Item -ItemType Directory -Path (Split-Path $WatchdogLog) -Force | Out-Null

function Write-WatchdogLog {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logLine = "[$timestamp] [$Level] $Message"
    Write-Host $logLine
    Add-Content -Path $WatchdogLog -Value $logLine -Encoding UTF8
}

function Get-LatestLogFile {
    $logFiles = Get-ChildItem "$ProjectRoot\logs\polygon_ingest_*.log" |
                Sort-Object LastWriteTime -Descending
    if ($logFiles) { return $logFiles[0] }
    return $null
}

function Get-ProcessByPIDFile {
    $pidFiles = Get-ChildItem "$ProjectRoot\logs\polygon_ingest_*.pid" |
                Sort-Object LastWriteTime -Descending
    if (-not $pidFiles) { return $null }

    $pidFile = $pidFiles[0]
    try {
        $processId = [int](Get-Content $pidFile.FullName -ErrorAction Stop)
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process) {
            Write-WatchdogLog "Found active process: PID $processId"
            return @{
                Process = $process
                ProcessId = $processId
                PIDFile = $pidFile
            }
        }
    } catch {
        Write-WatchdogLog "Error reading PID file: $_" -Level "WARN"
    }
    return $null
}

function Test-ProcessStalled {
    param($LogFile, $TimeoutSeconds)

    if (-not $LogFile -or -not (Test-Path $LogFile)) {
        return $false
    }

    $lastWrite = (Get-Item $LogFile).LastWriteTime
    $elapsed = (Get-Date) - $lastWrite

    if ($elapsed.TotalSeconds -gt $TimeoutSeconds) {
        Write-WatchdogLog "Process appears stalled. Log not updated for $([math]::Round($elapsed.TotalSeconds, 0))s" -Level "WARN"
        return $true
    }

    return $false
}

function Start-PolygonIngestion {
    param($RetryCount)

    Write-WatchdogLog "Launching Polygon ingestion (attempt $RetryCount)..."

    try {
        $launcher = Join-Path $ProjectRoot "tools\fase_3.2\launch_polygon_ingest.py"
        $args = @(
            $launcher,
            "--manifest", $Manifest,
            "--rate-limit", $RateLimit,
            "--quotes-hz", $QuotesHz
        )

        $process = Start-Process -FilePath "python" -ArgumentList $args -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden

        Start-Sleep -Seconds 5  # Wait for process to initialize

        # Verify it started
        if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
            Write-WatchdogLog "[OK] Process launched with PID: $($process.Id)"
            return $process.Id
        } else {
            Write-WatchdogLog "Process failed to start" -Level "ERROR"
            return $null
        }
    } catch {
        Write-WatchdogLog "Failed to launch process: $_" -Level "ERROR"
        return $null
    }
}

# ================================================================================
# MAIN WATCHDOG LOOP
# ================================================================================

Write-WatchdogLog "=========================================="
Write-WatchdogLog "WATCHDOG FASE 3.2 - STARTING"
Write-WatchdogLog "=========================================="
Write-WatchdogLog "Manifest: $Manifest"
Write-WatchdogLog "Rate limit: $RateLimit s"
Write-WatchdogLog "Check interval: $CheckIntervalSeconds s"
Write-WatchdogLog "Stall timeout: $StallTimeoutSeconds s"
Write-WatchdogLog "Max retries: $MaxRetries"
Write-WatchdogLog "To pause: Create file RUN_PAUSED.flag"
Write-WatchdogLog "=========================================="
Write-Host ""

$consecutiveFailures = 0
$totalRestarts = 0

while ($true) {
    # Check for pause flag
    if (Test-Path $PauseFlagFile) {
        Write-WatchdogLog "Pause flag detected. Stopping watchdog." -Level "INFO"
        Write-WatchdogLog "To resume: Delete RUN_PAUSED.flag and restart watchdog"
        break
    }

    # Check if process is running
    $processInfo = Get-ProcessByPIDFile

    if ($processInfo) {
        # Process is running, check if stalled
        $logFile = Get-LatestLogFile

        if (Test-ProcessStalled -LogFile $logFile -TimeoutSeconds $StallTimeoutSeconds) {
            Write-WatchdogLog "Process stalled. Terminating PID $($processInfo.ProcessId)..." -Level "WARN"

            try {
                Stop-Process -Id $processInfo.ProcessId -Force -ErrorAction Stop
                Start-Sleep -Seconds 3
                Write-WatchdogLog "Process terminated"
            } catch {
                Write-WatchdogLog "Error terminating process: $_" -Level "ERROR"
            }

            # Will relaunch in next iteration
            $consecutiveFailures++
            $totalRestarts++
        } else {
            # Process is healthy
            if ($consecutiveFailures -gt 0) {
                Write-WatchdogLog "Process recovered. Resetting failure counter."
                $consecutiveFailures = 0
            }
        }
    } else {
        # Process is not running - need to launch
        Write-WatchdogLog "No active process found. Launching..." -Level "WARN"

        if ($consecutiveFailures -ge $MaxRetries) {
            Write-WatchdogLog "Max retries ($MaxRetries) reached. Stopping watchdog." -Level "ERROR"
            Write-WatchdogLog "Manual intervention required. Check logs for errors."
            break
        }

        # Backoff if there were recent failures
        if ($consecutiveFailures -gt 0) {
            $backoffTime = $BackoffSeconds * [math]::Pow(2, $consecutiveFailures - 1)
            $backoffTime = [math]::Min($backoffTime, 900)  # Max 15 minutes
            Write-WatchdogLog "Backing off for $backoffTime seconds before retry..." -Level "WARN"
            Start-Sleep -Seconds $backoffTime
        }

        $newPid = Start-PolygonIngestion -RetryCount ($consecutiveFailures + 1)

        if ($newPid) {
            $consecutiveFailures = 0
            $totalRestarts++
            Write-WatchdogLog "Total restarts this session: $totalRestarts"
        } else {
            $consecutiveFailures++
            Write-WatchdogLog "Launch failed. Consecutive failures: $consecutiveFailures" -Level "ERROR"
        }
    }

    # Wait before next check
    Write-WatchdogLog "Next check in $CheckIntervalSeconds seconds..."
    Start-Sleep -Seconds $CheckIntervalSeconds
}

Write-WatchdogLog "=========================================="
Write-WatchdogLog "WATCHDOG FASE 3.2 - STOPPED"
Write-WatchdogLog "Total restarts: $totalRestarts"
Write-WatchdogLog "=========================================="
