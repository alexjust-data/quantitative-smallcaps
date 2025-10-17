# ================================================================================
# BACKUP DE DATOS - TRADING SMALLCAPS
# ================================================================================
# Backup completo con inventory, hashes SHA256 y documentación
# Prioridad: raw/, processed/, logs, docs, checkpoints
# Uso: .\backup_data.ps1 -BackupPath "E:\Backups"
# ================================================================================

param(
    [Parameter(Mandatory=$false)]
    [string]$BackupPath = "C:\Backups\TRADING_DATA"
)

$ProjectRoot = "D:\04_TRADING_SMALLCAPS"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = Join-Path $BackupPath "backup_$Timestamp"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "BACKUP DE DATOS - TRADING SMALLCAPS" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan
Write-Host "Timestamp: $Timestamp" -ForegroundColor Yellow
Write-Host "Destino: $BackupDir`n" -ForegroundColor White

# Crear directorio de backup
New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null

# Cambiar al directorio del proyecto
Push-Location $ProjectRoot

# ================================================================================
# PASO 1: BACKUP DE RAW DATA (DATOS CRUDOS DE MERCADO)
# ================================================================================
Write-Host "[1/2] Respaldando RAW DATA..." -ForegroundColor Yellow
$RawSource = Join-Path $ProjectRoot "raw"
$RawDest = Join-Path $BackupDir "raw"

if (Test-Path $RawSource) {
    Write-Host "  Copiando raw/ ..." -ForegroundColor Cyan
    Copy-Item -Path $RawSource -Destination $RawDest -Recurse -Force

    $rawSize = (Get-ChildItem $RawDest -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1GB
    Write-Host "  ✓ Raw data respaldado: $([math]::Round($rawSize, 2)) GB" -ForegroundColor Green
} else {
    Write-Host "  ⚠ Carpeta raw/ no encontrada" -ForegroundColor Yellow
}

# ================================================================================
# PASO 2: BACKUP DE PROCESSED DATA (EVENTOS, MANIFIESTOS, REFERENCIAS)
# ================================================================================
Write-Host "`n[2/5] Respaldando PROCESSED DATA..." -ForegroundColor Yellow
$ProcessedSource = Join-Path $ProjectRoot "processed"
$ProcessedDest = Join-Path $BackupDir "processed"

if (Test-Path $ProcessedSource) {
    Write-Host "  Copiando processed/ ..." -ForegroundColor Cyan
    Copy-Item -Path $ProcessedSource -Destination $ProcessedDest -Recurse -Force

    $processedSize = (Get-ChildItem $ProcessedDest -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1GB
    Write-Host "  ✓ Processed data respaldado: $([math]::Round($processedSize, 2)) GB" -ForegroundColor Green
} else {
    Write-Host "  ⚠ Carpeta processed/ no encontrada" -ForegroundColor Yellow
}

# ================================================================================
# PASO 3: BACKUP DE CHECKPOINTS Y LOGS
# ================================================================================
Write-Host "`n[3/5] Respaldando CHECKPOINTS y LOGS..." -ForegroundColor Yellow

# Checkpoints
$CheckpointsSource = Join-Path $ProjectRoot "logs\checkpoints"
$CheckpointsDest = Join-Path $BackupDir "logs\checkpoints"
if (Test-Path $CheckpointsSource) {
    Write-Host "  Copiando logs/checkpoints/ ..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $CheckpointsDest -Force | Out-Null
    Copy-Item -Path "$CheckpointsSource\*" -Destination $CheckpointsDest -Recurse -Force
    $cpCount = (Get-ChildItem $CheckpointsDest -File | Measure-Object).Count
    Write-Host "  ✓ Checkpoints respaldados: $cpCount archivos" -ForegroundColor Green
}

# Logs clave (últimos 7 días)
$LogsDest = Join-Path $BackupDir "logs\recent"
New-Item -ItemType Directory -Path $LogsDest -Force | Out-Null
$cutoffDate = (Get-Date).AddDays(-7)

$logPatterns = @(
    "logs\detect_events\*.log",
    "logs\worker_*.log",
    "logs\fase3.2_*.log",
    "logs\*.pid"
)

foreach ($pattern in $logPatterns) {
    Get-ChildItem $pattern -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt $cutoffDate } |
        ForEach-Object { Copy-Item $_.FullName -Destination $LogsDest -Force }
}

$logCount = (Get-ChildItem $LogsDest -File | Measure-Object).Count
Write-Host "  ✓ Logs recientes respaldados: $logCount archivos" -ForegroundColor Green

# ================================================================================
# PASO 4: BACKUP DE DOCUMENTACIÓN
# ================================================================================
Write-Host "`n[4/5] Respaldando DOCUMENTACIÓN..." -ForegroundColor Yellow
$DocsSource = Join-Path $ProjectRoot "docs\Daily"
$DocsDest = Join-Path $BackupDir "docs\Daily"

if (Test-Path $DocsSource) {
    Write-Host "  Copiando docs/Daily/ ..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Path (Split-Path $DocsDest) -Force | Out-Null
    Copy-Item -Path $DocsSource -Destination $DocsDest -Recurse -Force
    $docCount = (Get-ChildItem $DocsDest -File -Recurse | Measure-Object).Count
    Write-Host "  ✓ Documentación respaldada: $docCount archivos" -ForegroundColor Green
} else {
    Write-Host "  ⚠ Carpeta docs/Daily/ no encontrada" -ForegroundColor Yellow
}

# Scripts clave
Write-Host "  Copiando scripts clave..." -ForegroundColor Cyan
$ScriptsDest = Join-Path $BackupDir "scripts"
New-Item -ItemType Directory -Path $ScriptsDest -Force | Out-Null

$keyScripts = @(
    "scripts\processing\deduplicate_events.py",
    "scripts\ingestion\download_trades_quotes_intraday_v2.py",
    "scripts\execution\fase32\launch_pm_wave.py",
    "tools\watchdog_parallel.py"
)

foreach ($script in $keyScripts) {
    $scriptPath = Join-Path $ProjectRoot $script
    if (Test-Path $scriptPath) {
        $destScript = Join-Path $ScriptsDest (Split-Path $script -Leaf)
        Copy-Item $scriptPath -Destination $destScript -Force
    }
}

$scriptCount = (Get-ChildItem $ScriptsDest -File | Measure-Object).Count
Write-Host "  ✓ Scripts clave respaldados: $scriptCount archivos" -ForegroundColor Green

# ================================================================================
# PASO 5: INVENTORY Y HASHES SHA256
# ================================================================================
Write-Host "`n[5/5] Generando INVENTORY y HASHES..." -ForegroundColor Yellow

# Inventory CSV
Write-Host "  Generando inventory CSV..." -ForegroundColor Cyan
$inventoryPath = Join-Path $BackupDir "INVENTORY_$Timestamp.csv"
Get-ChildItem $BackupDir -Recurse -File |
    Select-Object @{N='RelativePath';E={$_.FullName.Replace("$BackupDir\","")}},
                  @{N='SizeBytes';E={$_.Length}},
                  @{N='SizeMB';E={[math]::Round($_.Length/1MB,2)}},
                  LastWriteTime,
                  Extension |
    Export-Csv $inventoryPath -NoTypeInformation -Encoding UTF8
Write-Host "  ✓ Inventory guardado: INVENTORY_$Timestamp.csv" -ForegroundColor Green

# SHA256 Hashes de archivos críticos
Write-Host "  Calculando hashes SHA256..." -ForegroundColor Cyan
$hashesPath = Join-Path $BackupDir "HASHES_$Timestamp.txt"
$hashReport = @()
$hashReport += "# SHA256 Hashes - Backup $Timestamp"
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
    $fullPath = Join-Path $BackupDir $file
    if (Test-Path $fullPath) {
        $hash = Get-FileHash $fullPath -Algorithm SHA256
        $hashReport += "$($hash.Hash)  $file"
    }
}

$hashReport | Out-File $hashesPath -Encoding UTF8
Write-Host "  ✓ Hashes guardados: HASHES_$Timestamp.txt" -ForegroundColor Green

# ================================================================================
# RESUMEN
# ================================================================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "BACKUP COMPLETADO" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

$TotalSize = (Get-ChildItem $BackupDir -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1GB
$FileCount = (Get-ChildItem $BackupDir -Recurse -File | Measure-Object).Count

Write-Host "Tamaño total: $([math]::Round($TotalSize, 2)) GB" -ForegroundColor White
Write-Host "Archivos: $FileCount" -ForegroundColor White
Write-Host "Ubicación: $BackupDir`n" -ForegroundColor White

# Crear README mejorado
$ReadmeContent = @'
BACKUP DE DATOS - TRADING SMALLCAPS
====================================
Fecha: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Snapshot ID: backup_$Timestamp
Tamano: $([math]::Round($TotalSize, 2)) GB
Archivos: $FileCount

CONTENIDO DEL BACKUP
--------------------

1. raw/                       - Datos crudos de mercado
2. processed/final/           - Dataset MASTER deduplicado (572,850 eventos)
3. processed/events/          - Consolidados por run + manifests
4. logs/checkpoints/          - Checkpoints de progreso
5. logs/recent/               - Logs de ultimos 7 dias
6. docs/Daily/                - Documentacion completa de fases
7. scripts/                   - Scripts clave de procesamiento
8. INVENTORY_$Timestamp.csv   - Inventario completo de archivos
9. HASHES_$Timestamp.txt      - SHA256 de archivos criticos

FASE 2.5 - DATASET FINAL (CERTIFICADO)
---------------------------------------

Master Dataset: processed/final/events_intraday_MASTER_dedup_v2.parquet
- Eventos unicos: 572,850
- Simbolos unicos: 1,621
- Cobertura temporal: 2022-10-10 a 2025-10-09 (3 anos)
- Tamano: 21.2 MB
- Calidad: 0% duplicados, 0% nulls
- Estado: CERTIFICADO para Fase 3.2

Consolidacion:
- Fuentes: 50 archivos (3 consolidados + 47 shards run 20251014)
- Input pre-dedup: 1,203,277 eventos
- Duplicados removidos: 630,427 (52.4%)
- Output final: 572,850 eventos unicos

VERIFICACION DE INTEGRIDAD
---------------------------

1. Verificar hashes SHA256:
   - Consultar HASHES_$Timestamp.txt
   - Comparar con archivos restaurados

2. Verificar inventario completo:
   - Consultar INVENTORY_$Timestamp.csv
   - Verificar conteo de archivos

3. Verificar dataset master:
   - Archivo: processed/final/events_intraday_MASTER_dedup_v2.parquet
   - Tamano esperado: ~21.2 MB
   - Eventos esperados: 572,850

PROCEDIMIENTO DE RESTAURACION
------------------------------

Restauracion completa:
1. Copiar backup_$Timestamp/ al destino
2. Verificar hashes (HASHES_$Timestamp.txt)
3. Copiar contenido a D:\04_TRADING_SMALLCAPS\

Restauracion parcial (solo dataset final):
1. Copiar processed/final/ a D:\04_TRADING_SMALLCAPS\processed\final\
2. Verificar hash del archivo MASTER_dedup_v2.parquet

Resume desde checkpoint:
1. Restaurar logs/checkpoints/
2. Lanzar watchdog: python tools/watchdog_parallel.py
3. El sistema continuara desde ultimo checkpoint

IMPORTANTE
----------

- Estos datos representan ~6 horas de procesamiento de Fase 2.5
- Los datos raw pueden re-descargarse pero cuesta API calls
- Los datos processed son irreemplazables (resultado de procesamiento)
- Los checkpoints permiten resume en caso de interrupcion
- La documentacion (docs/Daily/) contiene auditorias completas

DOCUMENTACION DE REFERENCIA
----------------------------

docs/Daily/fase_4/12_fase_25_auditoria_final.md
docs/Daily/fase_4/13_fase_25_consolidacion_maestra_FINAL.md
docs/Daily/fase_4/14_validacion_final_dataset_fase_25.md
docs/Daily/fase_5/01_fase_32_inicio.md

BACKUP COMPLETADO EXITOSAMENTE
'@

# Reemplazar placeholders
$ReadmeContent = $ReadmeContent.Replace('$(Get-Date -Format "yyyy-MM-dd HH:mm:ss")', (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
$ReadmeContent = $ReadmeContent.Replace('backup_$Timestamp', "backup_$Timestamp")
$ReadmeContent = $ReadmeContent.Replace('$([math]::Round($TotalSize, 2))', [math]::Round($TotalSize, 2))
$ReadmeContent = $ReadmeContent.Replace('$FileCount', $FileCount)
$ReadmeContent = $ReadmeContent.Replace('HASHES_$Timestamp.txt', "HASHES_$Timestamp.txt")
$ReadmeContent = $ReadmeContent.Replace('INVENTORY_$Timestamp.csv', "INVENTORY_$Timestamp.csv")

Set-Content -Path (Join-Path $BackupDir "README.txt") -Value $ReadmeContent
Write-Host "[OK] README.txt creado con metricas de Fase 2.5" -ForegroundColor Green
Write-Host ""

# Volver al directorio original
Pop-Location
