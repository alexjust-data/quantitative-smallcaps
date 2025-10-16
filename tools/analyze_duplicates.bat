@echo off
REM ================================================================================
REM FASE 2.5 - Duplicate Analysis Wrapper (Windows)
REM ================================================================================

echo.
echo ================================================================================
echo FASE 2.5 - DUPLICATE EVENTS ANALYSIS
echo ================================================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.8+
    exit /b 1
)

REM Check if polars is installed
python -c "import polars" 2>nul
if errorlevel 1 (
    echo ERROR: polars not installed
    echo Install with: pip install polars
    exit /b 1
)

REM Run analysis
python tools\analyze_duplicates.py %*

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ================================================================================
    echo Analysis completed successfully
    echo ================================================================================
    echo.
) else (
    echo.
    echo ================================================================================
    echo Analysis failed with exit code: %ERRORLEVEL%
    echo ================================================================================
    echo.
)

exit /b %ERRORLEVEL%
