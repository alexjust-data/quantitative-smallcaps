# ================================================================================
# BACKUP SNAPSHOT - TRADING SMALLCAPS
# ================================================================================
# Creates reproducible backup snapshot with inventory and SHA256 hashes
# Usage: .\tools\backup_snapshot.ps1 [-DestRoot "D:\BACKUPS"] [-Label "custom"]
# ================================================================================

param(
    [string]$DestRoot = "D:\BACKUPS_SMALLCAPS",
    [string]$Label = (Get-Date -Format "yyyyMMdd_HHmmss")
)

$ErrorActionPreference = "Stop"

# Snapshot directory
$dest = Join-Path $DestRoot "snapshot_$Label"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "BACKUP SNAPSHOT - TRADING SMALLCAPS" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Label: $Label" -ForegroundColor Yellow
Write-Host "Destination: $dest" -ForegroundColor White
Write-Host ""

# Create destination
New-Item -ItemType Directory -Force -Path $dest | Out-Null

# Use robocopy for efficient mirroring
Write-Host "[1/3] Copying data with robocopy..." -ForegroundColor Yellow
Write-Host ""

$sources = @(
    "processed\final",
    "processed\events",
    "raw\trades",
    "raw\quotes",
    "logs\checkpoints",
    "docs\Daily"
)

foreach ($src in $sources) {
    if (Test-Path $src) {
        Write-Host "  Copying $src..." -ForegroundColor Cyan
        $srcFull = Join-Path (Get-Location) $src
        $dstFull = Join-Path $dest $src
        $result = robocopy $srcFull $dstFull /E /R:1 /W:1 /NFL /NDL /NP /MT:8
        # Robocopy exit codes: 0-7 success, 8+ error
        if ($LASTEXITCODE -lt 8) {
            Write-Host "    [OK]" -ForegroundColor Green
        } else {
            Write-Host "    [WARNING] Robocopy exit code: $LASTEXITCODE" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [SKIP] $src not found" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "[2/3] Generating inventory..." -ForegroundColor Yellow

# Inventory CSV
$report = Join-Path $dest "INVENTORY_$Label.csv"
Get-ChildItem $dest -Recurse -File |
    Select-Object @{N='RelativePath';E={$_.FullName.Replace("$dest\","")}},
                  @{N='SizeBytes';E={$_.Length}},
                  @{N='SizeMB';E={[math]::Round($_.Length/1MB,2)}},
                  LastWriteTime,
                  Extension |
    Export-Csv $report -NoTypeInformation -Encoding UTF8

Write-Host "  [OK] Inventory: INVENTORY_$Label.csv" -ForegroundColor Green

Write-Host ""
Write-Host "[3/3] Calculating SHA256 hashes..." -ForegroundColor Yellow

# Hash critical files
$hashFile = Join-Path $dest "HASHES_$Label.txt"
$hashLines = @()
$hashLines += "SHA256 Hashes - Snapshot $Label"
$hashLines += "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$hashLines += ""

$criticalFiles = @(
    "processed\final\events_intraday_MASTER_dedup_v2.parquet",
    "processed\final\events_intraday_MASTER_dedup_v2.stats.json",
    "processed\events\manifest_core_FULL.parquet"
)

foreach ($file in $criticalFiles) {
    $fullPath = Join-Path $dest $file
    if (Test-Path $fullPath) {
        Write-Host "  Hashing $file..." -ForegroundColor Cyan
        $hash = Get-FileHash $fullPath -Algorithm SHA256
        $hashLines += "$($hash.Hash)  $file"
    }
}

$hashLines | Out-File $hashFile -Encoding UTF8
Write-Host "  [OK] Hashes: HASHES_$Label.txt" -ForegroundColor Green

# Create README
Write-Host ""
Write-Host "Creating README..." -ForegroundColor Yellow

$totalSize = (Get-ChildItem $dest -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1GB
$fileCount = (Get-ChildItem $dest -Recurse -File | Measure-Object).Count

$readme = @"
BACKUP SNAPSHOT - TRADING SMALLCAPS
====================================

Snapshot ID: snapshot_$Label
Created: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Total Size: $([math]::Round($totalSize, 2)) GB
Total Files: $fileCount

CONTENTS
--------

processed/final/          - Final dataset (MASTER dedup v2)
processed/events/         - Event consolidados + manifests
raw/trades/               - Raw trades data from Polygon
raw/quotes/               - Raw quotes data from Polygon
logs/checkpoints/         - Progress checkpoints (resume capability)
docs/Daily/               - Complete documentation

INVENTORY_$Label.csv      - Complete file listing with sizes
HASHES_$Label.txt         - SHA256 hashes for verification

PHASE 2.5 DATASET
-----------------

Master: processed/final/events_intraday_MASTER_dedup_v2.parquet
Events: 572,850 unique
Symbols: 1,621 unique
Coverage: 2022-10-10 to 2025-10-09 (3 years)
Quality: 0% duplicates, 0% nulls
Status: CERTIFIED for Phase 3.2

VERIFICATION
------------

1. Check file integrity:
   Get-FileHash "processed\final\events_intraday_MASTER_dedup_v2.parquet" -Algorithm SHA256
   Compare with HASHES_$Label.txt

2. Review inventory:
   Import-Csv "INVENTORY_$Label.csv" | Measure-Object SizeBytes -Sum

3. Verify dataset:
   python -c "import polars as pl; df=pl.read_parquet('processed/final/events_intraday_MASTER_dedup_v2.parquet'); print(f'Events: {df.height}, Symbols: {df[\"symbol\"].n_unique()}')"

RESTORE
-------

To restore:
1. Copy snapshot_$Label/ to target location
2. Verify hashes match HASHES_$Label.txt
3. Copy contents to D:\04_TRADING_SMALLCAPS\

To resume processing from checkpoints:
1. Restore logs/checkpoints/
2. Run: python tools/watchdog_parallel.py
3. System will continue from last checkpoint

DOCUMENTATION
-------------

Complete audit trail available in:
- docs/Daily/fase_4/12_fase_25_auditoria_final.md
- docs/Daily/fase_4/13_fase_25_consolidacion_maestra_FINAL.md
- docs/Daily/fase_4/14_validacion_final_dataset_fase_25.md
- docs/Daily/fase_5/01_fase_32_inicio.md

====================================
Snapshot created successfully
====================================
"@

$readme | Out-File (Join-Path $dest "README.txt") -Encoding UTF8
Write-Host "  [OK] README.txt" -ForegroundColor Green

# Final summary
Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "SNAPSHOT COMPLETED" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Location: $dest" -ForegroundColor White
Write-Host "Size: $([math]::Round($totalSize, 2)) GB" -ForegroundColor White
Write-Host "Files: $fileCount" -ForegroundColor White
Write-Host ""
Write-Host "Verification files:" -ForegroundColor Cyan
Write-Host "  - INVENTORY_$Label.csv" -ForegroundColor White
Write-Host "  - HASHES_$Label.txt" -ForegroundColor White
Write-Host "  - README.txt" -ForegroundColor White
Write-Host ""
