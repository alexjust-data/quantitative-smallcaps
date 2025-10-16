@echo off
REM ================================================================================
REM QUICK CHECK - Version super ligera sin escaneo de archivos
REM ================================================================================

echo.
echo ================================================================================
echo QUICK SYSTEM CHECK
echo ================================================================================
echo.

echo [1/5] PROCESOS ACTIVOS
echo --------------------------------------------------------------------------------
powershell -Command "Get-WmiObject Win32_Process | Where-Object {$_.CommandLine -like '*detect_events*' -or $_.CommandLine -like '*watchdog*' -or $_.CommandLine -like '*launch_parallel*'} | Select-Object ProcessId, Name, CreationDate | Format-Table -AutoSize"

echo.
echo [2/5] MEMORIA
echo --------------------------------------------------------------------------------
powershell -Command "$mem = Get-WmiObject Win32_OperatingSystem; $totalGB = [math]::Round($mem.TotalVisibleMemorySize/1MB, 2); $freeGB = [math]::Round($mem.FreePhysicalMemory/1MB, 2); Write-Host \"Total: $totalGB GB\"; Write-Host \"Free: $freeGB GB\"; if ($freeGB -lt 2) {Write-Host 'WARNING: Poca memoria!' -ForegroundColor Red} else {Write-Host 'OK' -ForegroundColor Green}"

echo.
echo [3/5] DISCO
echo --------------------------------------------------------------------------------
powershell -Command "$disk = Get-PSDrive D; $freeGB = [math]::Round($disk.Free/1GB, 2); Write-Host \"Free: $freeGB GB\"; if ($freeGB -lt 5) {Write-Host 'WARNING: Poco espacio!' -ForegroundColor Red} else {Write-Host 'OK' -ForegroundColor Green}"

echo.
echo [4/5] LOCKS ZOMBIES
echo --------------------------------------------------------------------------------
powershell -Command "$locks = Get-ChildItem -Path 'logs\checkpoints', 'processed\events\shards' -Filter '*.lock' -Recurse -ErrorAction SilentlyContinue; if ($locks) {Write-Host \"Found $($locks.Count) lock files\" -ForegroundColor Yellow; $locks | Select-Object -First 5 Name, DirectoryName} else {Write-Host 'No locks found - OK' -ForegroundColor Green}"

echo.
echo [5/5] HEARTBEAT (ultimas 3 lineas)
echo --------------------------------------------------------------------------------
powershell -Command "$hb = Get-ChildItem 'logs\detect_events\heartbeat_*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if ($hb) {Write-Host \"File: $($hb.Name)\"; Get-Content $hb.FullName -Tail 3} else {Write-Host 'No heartbeat file'}"

echo.
echo ================================================================================
echo CHECK COMPLETADO
echo ================================================================================
echo.
echo Ejecuta: python restart_parallel.py
echo Para limpiar residuos antes de relanzar
echo.
