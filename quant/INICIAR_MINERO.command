#!/bin/bash
# Doble clic en macOS para iniciar el minero de estrategias.
cd "$(dirname "$0")" || exit 1
PY="./.venv/bin/python"
[ -x "$PY" ] || PY="python3"
echo "============================================"
echo "  Minero quantos — buscando estrategias"
echo "============================================"
echo "Deja esta ventana abierta mientras no estas."
echo 'El oro aparece en la app, seccion "Bóveda de oro". Cierra la ventana para detenerlo.'
"$PY" -m quantos.mining.run --symbol BTC/USDT
