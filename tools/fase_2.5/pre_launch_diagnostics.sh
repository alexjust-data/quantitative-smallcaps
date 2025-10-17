#!/bin/bash
# ================================================================================
# FASE 2.5 - Pre-Launch Diagnostics Wrapper (Bash)
# ================================================================================

# Change to project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT" || exit 1

echo ""
echo "================================================================================"
echo "FASE 2.5 - PRE-LAUNCH DIAGNOSTICS"
echo "================================================================================"
echo ""

# Check if Python is available
if ! command -v python &> /dev/null; then
    echo "ERROR: Python not found. Please install Python 3.8+"
    exit 1
fi

# Check if psutil is installed
python -c "import psutil" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "ERROR: psutil not installed"
    echo "Install with: pip install psutil"
    exit 1
fi

# Run diagnostics
python tools/pre_launch_diagnostics.py "$@"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "================================================================================"
    echo "✅ SAFE TO LAUNCH"
    echo "================================================================================"
    echo ""
else
    echo "================================================================================"
    echo "❌ NOT SAFE TO LAUNCH - Resolver issues primero"
    echo "================================================================================"
    echo ""
fi

exit $EXIT_CODE
