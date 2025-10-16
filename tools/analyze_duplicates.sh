#!/bin/bash
# ================================================================================
# FASE 2.5 - Duplicate Analysis Wrapper (Bash)
# ================================================================================

# Change to project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT" || exit 1

echo ""
echo "================================================================================"
echo "FASE 2.5 - DUPLICATE EVENTS ANALYSIS"
echo "================================================================================"
echo ""

# Check if Python is available
if ! command -v python &> /dev/null; then
    echo "ERROR: Python not found. Please install Python 3.8+"
    exit 1
fi

# Check if polars is installed
python -c "import polars" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "ERROR: polars not installed"
    echo "Install with: pip install polars"
    exit 1
fi

# Run analysis
python tools/analyze_duplicates.py "$@"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "================================================================================"
    echo "Analysis completed successfully"
    echo "================================================================================"
    echo ""
else
    echo ""
    echo "================================================================================"
    echo "Analysis failed with exit code: $EXIT_CODE"
    echo "================================================================================"
    echo ""
fi

exit $EXIT_CODE
