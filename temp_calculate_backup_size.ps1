# Calculate backup size estimate
$ProjectRoot = "D:\04_TRADING_SMALLCAPS"
Push-Location $ProjectRoot

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "ESTIMACION DE TAMANO DE BACKUP" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$totalSize = 0

# 1. RAW DATA
Write-Host "[1/5] Calculando raw/..." -ForegroundColor Yellow
if (Test-Path "raw") {
    $rawSize = (Get-ChildItem "raw" -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    $rawGB = [math]::Round($rawSize / 1GB, 2)
    $rawMB = [math]::Round($rawSize / 1MB, 0)
    Write-Host "  raw/: $rawGB GB ($rawMB MB)" -ForegroundColor White
    $totalSize += $rawSize
} else {
    Write-Host "  raw/: No existe" -ForegroundColor Yellow
}

# 2. PROCESSED DATA
Write-Host "`n[2/5] Calculando processed/..." -ForegroundColor Yellow
if (Test-Path "processed") {
    $processedSize = (Get-ChildItem "processed" -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    $processedGB = [math]::Round($processedSize / 1GB, 2)
    $processedMB = [math]::Round($processedSize / 1MB, 0)
    Write-Host "  processed/: $processedGB GB ($processedMB MB)" -ForegroundColor White
    $totalSize += $processedSize

    # Detalle de processed/
    if (Test-Path "processed\final") {
        $finalSize = (Get-ChildItem "processed\final" -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $finalMB = [math]::Round($finalSize / 1MB, 1)
        Write-Host "    - processed/final/: $finalMB MB" -ForegroundColor Gray
    }
    if (Test-Path "processed\events") {
        $eventsSize = (Get-ChildItem "processed\events" -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $eventsMB = [math]::Round($eventsSize / 1MB, 1)
        Write-Host "    - processed/events/: $eventsMB MB" -ForegroundColor Gray
    }
} else {
    Write-Host "  processed/: No existe" -ForegroundColor Yellow
}

# 3. LOGS Y CHECKPOINTS
Write-Host "`n[3/5] Calculando logs/ y checkpoints..." -ForegroundColor Yellow
$logsSize = 0

# Checkpoints
if (Test-Path "logs\checkpoints") {
    $cpSize = (Get-ChildItem "logs\checkpoints" -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    $logsSize += $cpSize
    $cpMB = [math]::Round($cpSize / 1MB, 1)
    Write-Host "  logs/checkpoints/: $cpMB MB" -ForegroundColor White
}

# Logs recientes (últimos 7 días)
$cutoffDate = (Get-Date).AddDays(-7)
$logPatterns = @("logs\detect_events\*.log", "logs\worker_*.log", "logs\fase3.2_*.log", "logs\*.pid")
$recentLogs = 0
foreach ($pattern in $logPatterns) {
    $files = Get-ChildItem $pattern -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -gt $cutoffDate }
    if ($files) {
        $recentLogs += ($files | Measure-Object -Property Length -Sum).Sum
    }
}
$logsSize += $recentLogs
$recentMB = [math]::Round($recentLogs / 1MB, 1)
Write-Host "  logs/recent/ (últimos 7 días): $recentMB MB" -ForegroundColor White

$logsTotalMB = [math]::Round($logsSize / 1MB, 1)
Write-Host "  Total logs: $logsTotalMB MB" -ForegroundColor White
$totalSize += $logsSize

# 4. DOCUMENTACIÓN
Write-Host "`n[4/5] Calculando docs/..." -ForegroundColor Yellow
if (Test-Path "docs\Daily") {
    $docsSize = (Get-ChildItem "docs\Daily" -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    $docsMB = [math]::Round($docsSize / 1MB, 1)
    Write-Host "  docs/Daily/: $docsMB MB" -ForegroundColor White
    $totalSize += $docsSize
} else {
    Write-Host "  docs/Daily/: No existe" -ForegroundColor Yellow
}

# 5. SCRIPTS CLAVE
Write-Host "`n[5/5] Calculando scripts clave..." -ForegroundColor Yellow
$keyScripts = @(
    "scripts\processing\deduplicate_events.py",
    "scripts\ingestion\download_trades_quotes_intraday_v2.py",
    "scripts\execution\fase32\launch_pm_wave.py",
    "tools\watchdog_parallel.py"
)
$scriptsSize = 0
foreach ($script in $keyScripts) {
    if (Test-Path $script) {
        $scriptsSize += (Get-Item $script).Length
    }
}
$scriptsMB = [math]::Round($scriptsSize / 1MB, 2)
Write-Host "  scripts/: $scriptsMB MB" -ForegroundColor White
$totalSize += $scriptsSize

# RESUMEN
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "RESUMEN" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$totalGB = [math]::Round($totalSize / 1GB, 2)
$totalMB = [math]::Round($totalSize / 1MB, 0)

Write-Host "`nTamano total sin comprimir: $totalGB GB ($totalMB MB)" -ForegroundColor White

# Estimacion de compresion (conservadora)
# Parquet files: ~20-30% del original
# Logs: ~10-20% del original
# Markdown: ~30-40% del original

$estimatedCompressedSize = $totalSize * 0.25  # 25% promedio conservador
$compressedGB = [math]::Round($estimatedCompressedSize / 1GB, 2)
$compressedMB = [math]::Round($estimatedCompressedSize / 1MB, 0)

Write-Host "Tamano estimado comprimido: $compressedGB GB ($compressedMB MB)" -ForegroundColor Yellow
Write-Host "  (Ratio estimado: 25% del original)" -ForegroundColor Gray

# Verificar espacio disponible
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "ESPACIO DISPONIBLE EN DISCOS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Free -ne $null } | ForEach-Object {
    $freeGB = [math]::Round($_.Free / 1GB, 2)
    $usedGB = [math]::Round($_.Used / 1GB, 2)
    $totalDiskGB = [math]::Round(($_.Free + $_.Used) / 1GB, 2)
    $pctUsed = [math]::Round(($_.Used / ($_.Free + $_.Used)) * 100, 1)
    Write-Host "`n$($_.Name):\ - $totalDiskGB GB total" -ForegroundColor White
    Write-Host "  Usado: $usedGB GB ($pctUsed%)" -ForegroundColor Gray
    Write-Host "  Libre: $freeGB GB" -ForegroundColor Green

    # Verificar si hay espacio suficiente
    if ($_.Free -gt ($totalSize * 1.1)) {
        Write-Host "  [OK] Espacio suficiente para backup sin comprimir" -ForegroundColor Green
    } elseif ($_.Free -gt ($estimatedCompressedSize * 1.1)) {
        Write-Host "  [WARNING] Solo espacio suficiente para backup COMPRIMIDO" -ForegroundColor Yellow
    } else {
        Write-Host "  [ERROR] Espacio insuficiente" -ForegroundColor Red
    }
}

Pop-Location
