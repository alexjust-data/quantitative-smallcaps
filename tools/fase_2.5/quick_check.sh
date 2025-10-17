#!/bin/bash
# ================================================================================
# QUICK CHECK - Version super ligera sin escaneo de archivos
# ================================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT" || exit 1

echo ""
echo "================================================================================"
echo "QUICK SYSTEM CHECK"
echo "================================================================================"
echo ""

echo "[1/5] PROCESOS ACTIVOS"
echo "--------------------------------------------------------------------------------"
ps aux | grep -E "(detect_events|watchdog|launch_parallel)" | grep python | grep -v grep || echo "No hay procesos activos"

echo ""
echo "[2/5] MEMORIA"
echo "--------------------------------------------------------------------------------"
if command -v free &> /dev/null; then
    free -h | grep Mem
else
    echo "Comando 'free' no disponible en Windows Git Bash"
    echo "Usar: quick_check.bat desde CMD"
fi

echo ""
echo "[3/5] DISCO"
echo "--------------------------------------------------------------------------------"
df -h . | tail -1

echo ""
echo "[4/5] LOCKS ZOMBIES"
echo "--------------------------------------------------------------------------------"
locks=$(find logs/checkpoints processed/events/shards -name "*.lock" 2>/dev/null)
if [ -n "$locks" ]; then
    echo "WARNING: Lock files encontrados:"
    echo "$locks" | head -5
    count=$(echo "$locks" | wc -l)
    echo "Total: $count locks"
else
    echo "No hay locks - OK"
fi

echo ""
echo "[5/5] HEARTBEAT (ultimas 3 lineas)"
echo "--------------------------------------------------------------------------------"
hb=$(ls -t logs/detect_events/heartbeat_*.log 2>/dev/null | head -1)
if [ -n "$hb" ]; then
    echo "File: $(basename $hb)"
    tail -3 "$hb"
else
    echo "No heartbeat file"
fi

echo ""
echo "================================================================================"
echo "CHECK COMPLETADO"
echo "================================================================================"
echo ""
echo "Ejecuta: python restart_parallel.py"
echo "Para limpiar residuos antes de relanzar"
echo ""
