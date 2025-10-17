# ================================================================================
# BACKUP COMPRIMIDO DE DATOS - TRADING SMALLCAPS
# ================================================================================
# Crea backup completo en formato .zip con inventory y hashes SHA256
# Incluye: raw/, processed/, logs, docs, checkpoints
# Uso: .\backup_data_compressed.ps1 -BackupPath "E:\Backups"
# ================================================================================

param(
    [Parameter(Mandatory=$false)]
    [string]$BackupPath = "C:\Backups\TRADING_DATA"
)

$ProjectRoot = "D:\04_TRADING_SMALLCAPS"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$TempDir = Join-Path $env:TEMP "backup_staging_$Timestamp"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "BACKUP COMPRIMIDO DE DATOS" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan
Write-Host "Timestamp: $Timestamp" -ForegroundColor Yellow
Write-Host "Destino: $BackupPath`n" -ForegroundColor White

# Crear directorio de backup y staging
New-Item -ItemType Directory -Path $BackupPath -Force | Out-Null
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

# Cambiar al directorio del proyecto
Push-Location $ProjectRoot

# ================================================================================
# PASO 1: COPIAR A STAGING (para compresión)
# ================================================================================
Write-Host "[1/6] Copiando datos a staging..." -ForegroundColor Yellow

# Raw data
if (Test-Path "raw") {
    Write-Host "  Copiando raw/..." -ForegroundColor Cyan
    Copy-Item -Path "raw" -Destination "$TempDir\raw" -Recurse -Force
    Write-Host "  ✓ Raw copiado" -ForegroundColor Green
}

# Processed data
if (Test-Path "processed") {
    Write-Host "  Copiando processed/..." -ForegroundColor Cyan
    Copy-Item -Path "processed" -Destination "$TempDir\processed" -Recurse -Force
    Write-Host "  ✓ Processed copiado" -ForegroundColor Green
}

# ================================================================================
# PASO 2: LOGS Y CHECKPOINTS
# ================================================================================
Write-Host "`n[2/6] Copiando logs y checkpoints..." -ForegroundColor Yellow

# Checkpoints
if (Test-Path "logs\checkpoints") {
    New-Item -ItemType Directory -Path "$TempDir\logs\checkpoints" -Force | Out-Null
    Copy-Item -Path "logs\checkpoints\*" -Destination "$TempDir\logs\checkpoints\" -Recurse -Force
    Write-Host "  ✓ Checkpoints copiados" -ForegroundColor Green
}

# Logs recientes (últimos 7 días)
$cutoffDate = (Get-Date).AddDays(-7)
$LogsTemp = "$TempDir\logs\recent"
New-Item -ItemType Directory -Path $LogsTemp -Force | Out-Null

$logPatterns = @("logs\detect_events\*.log", "logs\worker_*.log", "logs\fase3.2_*.log", "logs\*.pid")
foreach ($pattern in $logPatterns) {
    Get-ChildItem $pattern -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt $cutoffDate } |
        ForEach-Object { Copy-Item $_.FullName -Destination $LogsTemp -Force }
}
Write-Host "  ✓ Logs recientes copiados" -ForegroundColor Green

# ================================================================================
# PASO 3: DOCUMENTACIÓN Y SCRIPTS
# ================================================================================
Write-Host "`n[3/6] Copiando documentación y scripts..." -ForegroundColor Yellow

# Docs
if (Test-Path "docs\Daily") {
    Copy-Item -Path "docs\Daily" -Destination "$TempDir\docs\Daily" -Recurse -Force
    Write-Host "  ✓ Documentación copiada" -ForegroundColor Green
}

# Scripts clave
$ScriptsDest = "$TempDir\scripts"
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
Write-Host "  ✓ Scripts clave copiados" -ForegroundColor Green

# ================================================================================
# PASO 4: GENERAR INVENTORY Y HASHES
# ================================================================================
Write-Host "`n[4/6] Generando inventory y hashes..." -ForegroundColor Yellow

# Inventory
$inventoryPath = "$TempDir\INVENTORY_$Timestamp.csv"
Get-ChildItem $TempDir -Recurse -File |
    Select-Object @{N='RelativePath';E={$_.FullName.Replace("$TempDir\","")}},
                  @{N='SizeBytes';E={$_.Length}},
                  @{N='SizeMB';E={[math]::Round($_.Length/1MB,2)}},
                  LastWriteTime,
                  Extension |
    Export-Csv $inventoryPath -NoTypeInformation -Encoding UTF8
Write-Host "  ✓ Inventory generado" -ForegroundColor Green

# Hashes SHA256
$hashesPath = "$TempDir\HASHES_$Timestamp.txt"
$hashReport = @()
$hashReport += "# SHA256 Hashes - Backup Comprimido $Timestamp"
$hashReport += "# Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$hashReport += ""

$criticalFiles = @(
    "processed\final\events_intraday_MASTER_dedup_v2.parquet",
    "processed\final\events_intraday_MASTER_dedup_v2.stats.json",
    "processed\events\events_intraday_20251012.parquet",
    "processed\events\events_intraday_20251013.parquet",
    "processed\events\events_intraday_20251016.parquet"
)

foreach ($file in $criticalFiles) {
    $fullPath = Join-Path $TempDir $file
    if (Test-Path $fullPath) {
        $hash = Get-FileHash $fullPath -Algorithm SHA256
        $hashReport += "$($hash.Hash)  $file"
    }
}
$hashReport | Out-File $hashesPath -Encoding UTF8
Write-Host "  ✓ Hashes SHA256 calculados" -ForegroundColor Green

# README
$stagingSize = (Get-ChildItem $TempDir -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1GB
$ReadmeContent = @"
================================================================================
BACKUP COMPRIMIDO - TRADING SMALLCAPS
================================================================================
Fecha: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Snapshot ID: backup_compressed_$Timestamp
Tamaño sin comprimir: $([math]::Round($stagingSize, 2)) GB

Este es un backup COMPRIMIDO. Descomprimir antes de usar.
Ver INVENTORY_$Timestamp.csv y HASHES_$Timestamp.txt para verificación.

FASE 2.5 - Dataset Final: 572,850 eventos, 1,621 símbolos (CERTIFICADO)
Ver README completo en backup sin comprimir para detalles completos.
================================================================================
"@
Set-Content -Path "$TempDir\README.txt" -Value $ReadmeContent

# ================================================================================
# PASO 5: COMPRIMIR TODO
# ================================================================================
Write-Host "`n[5/6] Comprimiendo backup completo..." -ForegroundColor Yellow
$CompressedZip = Join-Path $BackupPath "backup_compressed_$Timestamp.zip"

Write-Host "  Comprimiendo $([math]::Round($stagingSize, 2)) GB..." -ForegroundColor Cyan
Compress-Archive -Path "$TempDir\*" -DestinationPath $CompressedZip -CompressionLevel Optimal -Force

$compressedSize = (Get-Item $CompressedZip).Length / 1GB
$compressionRatio = [math]::Round(($compressedSize / $stagingSize) * 100, 1)
Write-Host "  ✓ Comprimido: $([math]::Round($compressedSize, 2)) GB ($compressionRatio% del original)" -ForegroundColor Green

# ================================================================================
# PASO 6: CLEANUP STAGING
# ================================================================================
Write-Host "`n[6/6] Limpiando staging..." -ForegroundColor Yellow
Remove-Item -Path $TempDir -Recurse -Force
Write-Host "  ✓ Staging limpiado" -ForegroundColor Green

# ================================================================================
# RESUMEN
# ================================================================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "BACKUP COMPRIMIDO COMPLETADO" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Archivo: backup_compressed_$Timestamp.zip" -ForegroundColor White
Write-Host "Ubicación: $BackupPath" -ForegroundColor White
Write-Host "Tamaño comprimido: $([math]::Round($compressedSize, 2)) GB" -ForegroundColor White
Write-Host "Tamaño original: $([math]::Round($stagingSize, 2)) GB" -ForegroundColor White
Write-Host "Ratio compresión: $compressionRatio%" -ForegroundColor White
Write-Host ""
Write-Host "Contenido incluido:" -ForegroundColor Cyan
Write-Host "  - raw/ (datos crudos)" -ForegroundColor White
Write-Host "  - processed/ (eventos + manifests)" -ForegroundColor White
Write-Host "  - logs/ (checkpoints + recientes)" -ForegroundColor White
Write-Host "  - docs/ (documentación completa)" -ForegroundColor White
Write-Host "  - scripts/ (scripts clave)" -ForegroundColor White
Write-Host "  - INVENTORY_$Timestamp.csv" -ForegroundColor White
Write-Host "  - HASHES_$Timestamp.txt" -ForegroundColor White
Write-Host "  - README.txt" -ForegroundColor White
Write-Host ""
Write-Host "Para descomprimir:" -ForegroundColor Yellow
Write-Host "  Expand-Archive -Path '$CompressedZip' -DestinationPath '<destino>'" -ForegroundColor Gray
Write-Host ""

# Volver al directorio original
Pop-Location
