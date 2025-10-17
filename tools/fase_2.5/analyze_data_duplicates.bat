@echo off
REM ================================================================================
REM FASE 2.5 - Data & Duplicates Analysis (Windows)
REM ================================================================================
REM
REM Analisis completo y 100%% verificable de datos fisicos y duplicados
REM
REM Usage:
REM   analyze_data_duplicates.bat         - Analisis completo
REM   analyze_data_duplicates.bat --quick - Analisis rapido (sin heartbeat)
REM
REM ================================================================================

echo.
echo ================================================================================
echo FASE 2.5 - ANALISIS DE DATOS Y DUPLICADOS
echo ================================================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found
    exit /b 1
)

python tools\analyze_data_duplicates.py %*

exit /b %ERRORLEVEL%
