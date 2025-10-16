@echo off
REM ================================================================================
REM FASE 2.5 - Pre-Launch Diagnostics Wrapper (Windows)
REM ================================================================================

echo.
echo ================================================================================
echo FASE 2.5 - PRE-LAUNCH DIAGNOSTICS
echo ================================================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.8+
    exit /b 1
)

REM Check if psutil is installed
python -c "import psutil" 2>nul
if errorlevel 1 (
    echo ERROR: psutil not installed
    echo Install with: pip install psutil
    exit /b 1
)

REM Run diagnostics
python tools\pre_launch_diagnostics.py %*

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ================================================================================
    echo [32m✅ SAFE TO LAUNCH[0m
    echo ================================================================================
    echo.
) else (
    echo.
    echo ================================================================================
    echo [31m❌ NOT SAFE TO LAUNCH - Resolver issues primero[0m
    echo ================================================================================
    echo.
)

exit /b %ERRORLEVEL%
