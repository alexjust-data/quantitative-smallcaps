#!/bin/bash
# ================================================================================
# FASE 2.5 - Data & Duplicates Analysis (Linux/Mac)
# ================================================================================
#
# Analisis completo y 100% verificable de datos fisicos y duplicados
#
# Usage:
#   ./analyze_data_duplicates.sh         - Analisis completo
#   ./analyze_data_duplicates.sh --quick - Analisis rapido (sin heartbeat)
#
# ================================================================================

echo
echo "================================================================================"
echo "FASE 2.5 - ANALISIS DE DATOS Y DUPLICADOS"
echo "================================================================================"
echo

python3 tools/analyze_data_duplicates.py "$@"
