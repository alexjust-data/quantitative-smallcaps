@echo off
REM Launch FASE 3.2 PM Wave
echo ========================================
echo LAUNCHING FASE 3.2 - PM WAVE
echo ========================================
echo.
echo Manifest: processed/events/manifest_core_20251014.parquet
echo Wave: PM (1,452 events)
echo Rate limit: 12s
echo Quotes Hz: 1
echo Resume: enabled
echo.
echo Output: logs/fase3.2_pm_wave.log
echo.
echo ========================================
echo.

start /B python scripts\ingestion\download_trades_quotes_intraday_v2.py --manifest processed\events\manifest_core_20251014.parquet --wave PM --rate-limit 12 --quotes-hz 1 --resume > logs\fase3.2_pm_wave.log 2>&1

echo Process launched in background
echo Check progress: tail -f logs/fase3.2_pm_wave.log
echo.
