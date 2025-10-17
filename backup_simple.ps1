# Simple Backup Script
$ProjectRoot = "D:\04_TRADING_SMALLCAPS"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupPath = "C:\Backups\TRADING_DATA"
$BackupDir = Join-Path $BackupPath "backup_$Timestamp"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "BACKUP - TRADING SMALLCAPS" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Timestamp: $Timestamp" -ForegroundColor Yellow
Write-Host "Destino: $BackupDir" -ForegroundColor White
Write-Host ""

# Create backup directory
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
Push-Location $ProjectRoot

# 1. RAW DATA
Write-Host "[1/5] Copiando raw/..." -ForegroundColor Yellow
if (Test-Path "raw") {
    Copy-Item -Path "raw" -Destination "$BackupDir\raw" -Recurse -Force
    $rawSize = (Get-ChildItem "$BackupDir\raw" -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1GB
    Write-Host "  [OK] Raw: $([math]::Round($rawSize, 2)) GB" -ForegroundColor Green
}

# 2. PROCESSED DATA
Write-Host ""
Write-Host "[2/5] Copiando processed/..." -ForegroundColor Yellow
if (Test-Path "processed") {
    Copy-Item -Path "processed" -Destination "$BackupDir\processed" -Recurse -Force
    $processedSize = (Get-ChildItem "$BackupDir\processed" -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1GB
    Write-Host "  [OK] Processed: $([math]::Round($processedSize, 2)) GB" -ForegroundColor Green
}

# 3. LOGS AND CHECKPOINTS
Write-Host ""
Write-Host "[3/5] Copiando logs y checkpoints..." -ForegroundColor Yellow

# Checkpoints
if (Test-Path "logs\checkpoints") {
    New-Item -ItemType Directory -Path "$BackupDir\logs\checkpoints" -Force | Out-Null
    Copy-Item -Path "logs\checkpoints\*" -Destination "$BackupDir\logs\checkpoints\" -Recurse -Force
    Write-Host "  [OK] Checkpoints copiados" -ForegroundColor Green
}

# Recent logs (last 7 days)
$cutoffDate = (Get-Date).AddDays(-7)
$LogsDest = "$BackupDir\logs\recent"
New-Item -ItemType Directory -Path $LogsDest -Force | Out-Null

$logPatterns = @("logs\detect_events\*.log", "logs\worker_*.log", "logs\fase3.2_*.log", "logs\*.pid")
foreach ($pattern in $logPatterns) {
    Get-ChildItem $pattern -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt $cutoffDate } |
        ForEach-Object { Copy-Item $_.FullName -Destination $LogsDest -Force }
}
Write-Host "  [OK] Logs recientes copiados" -ForegroundColor Green

# 4. DOCUMENTATION
Write-Host ""
Write-Host "[4/5] Copiando documentacion..." -ForegroundColor Yellow
if (Test-Path "docs\Daily") {
    Copy-Item -Path "docs\Daily" -Destination "$BackupDir\docs\Daily" -Recurse -Force
    Write-Host "  [OK] Documentacion copiada" -ForegroundColor Green
}

# Scripts
$ScriptsDest = "$BackupDir\scripts"
New-Item -ItemType Directory -Path $ScriptsDest -Force | Out-Null
$keyScripts = @(
    "scripts\processing\deduplicate_events.py",
    "scripts\ingestion\download_trades_quotes_intraday_v2.py",
    "scripts\execution\fase32\launch_pm_wave.py",
    "tools\watchdog_parallel.py"
)
foreach ($script in $keyScripts) {
    if (Test-Path $script) {
        Copy-Item $script -Destination "$ScriptsDest\$(Split-Path $script -Leaf)" -Force
    }
}
Write-Host "  [OK] Scripts copiados" -ForegroundColor Green

# 5. INVENTORY AND HASHES
Write-Host ""
Write-Host "[5/5] Generando inventory y hashes..." -ForegroundColor Yellow

# Inventory
$inventoryPath = "$BackupDir\INVENTORY_$Timestamp.csv"
Get-ChildItem $BackupDir -Recurse -File |
    Select-Object @{N='RelativePath';E={$_.FullName.Replace("$BackupDir\","")}},
                  @{N='SizeBytes';E={$_.Length}},
                  @{N='SizeMB';E={[math]::Round($_.Length/1MB,2)}},
                  LastWriteTime,
                  Extension |
    Export-Csv $inventoryPath -NoTypeInformation -Encoding UTF8
Write-Host "  [OK] Inventory: INVENTORY_$Timestamp.csv" -ForegroundColor Green

# Hashes
$hashesPath = "$BackupDir\HASHES_$Timestamp.txt"
$hashLines = @()
$hashLines += "SHA256 Hashes - Backup $Timestamp"
$hashLines += "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$hashLines += ""

$criticalFiles = @(
    "processed\final\events_intraday_MASTER_dedup_v2.parquet",
    "processed\final\events_intraday_MASTER_dedup_v2.stats.json"
)

foreach ($file in $criticalFiles) {
    $fullPath = Join-Path $BackupDir $file
    if (Test-Path $fullPath) {
        $hash = Get-FileHash $fullPath -Algorithm SHA256
        $hashLines += "$($hash.Hash)  $file"
    }
}
$hashLines | Out-File $hashesPath -Encoding UTF8
Write-Host "  [OK] Hashes: HASHES_$Timestamp.txt" -ForegroundColor Green

# README
$readmeText = "BACKUP SMALLCAPS - $Timestamp`n"
$readmeText += "================================`n`n"
$readmeText += "Backup created: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n`n"
$readmeText += "Contents:`n"
$readmeText += "- raw/ (market data)`n"
$readmeText += "- processed/ (events, manifests)`n"
$readmeText += "- logs/ (checkpoints, recent logs)`n"
$readmeText += "- docs/ (documentation)`n"
$readmeText += "- scripts/ (key scripts)`n"
$readmeText += "- INVENTORY_$Timestamp.csv`n"
$readmeText += "- HASHES_$Timestamp.txt`n`n"
$readmeText += "Phase 2.5 Dataset: 572,850 events, 1,621 symbols (CERTIFIED)`n"
$readmeText += "See documentation in docs/Daily/ for complete details.`n"

$readmeText | Out-File "$BackupDir\README.txt" -Encoding UTF8
Write-Host "  [OK] README.txt creado" -ForegroundColor Green

# SUMMARY
Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "BACKUP COMPLETADO" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan

$TotalSize = (Get-ChildItem $BackupDir -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1GB
$FileCount = (Get-ChildItem $BackupDir -Recurse -File | Measure-Object).Count

Write-Host ""
Write-Host "Tamano total: $([math]::Round($TotalSize, 2)) GB" -ForegroundColor White
Write-Host "Archivos: $FileCount" -ForegroundColor White
Write-Host "Ubicacion: $BackupDir" -ForegroundColor White
Write-Host ""

Pop-Location
