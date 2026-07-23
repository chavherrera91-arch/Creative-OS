#!/bin/bash
# Doble clic en macOS para instalar quantos como app de escritorio.
cd "$(dirname "$0")" || exit 1
echo "============================================"
echo "  Instalando quantos como app de escritorio"
echo "============================================"
if ! command -v python3 >/dev/null 2>&1; then
  echo "[!] No encontre Python. Instalalo desde https://www.python.org/downloads/"
  echo "    Luego vuelve a hacer doble clic en este archivo."
  read -r -p "Enter para cerrar..."
  exit 1
fi
python3 install_desktop.py
read -r -p "Listo. Enter para cerrar..."
