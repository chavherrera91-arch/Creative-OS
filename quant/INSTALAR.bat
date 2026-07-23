@echo off
title Instalar quantos
cd /d "%~dp0"
echo ============================================
echo   Instalando quantos como app de escritorio
echo ============================================
echo.
where python >nul 2>nul
if errorlevel 1 (
  echo [!] No encontre Python en tu PC.
  echo.
  echo     1^) Instalalo desde:  https://www.python.org/downloads/
  echo     2^) IMPORTANTE: marca la casilla "Add Python to PATH" al instalar.
  echo     3^) Vuelve a hacer doble clic en este archivo.
  echo.
  pause
  exit /b 1
)
python install_desktop.py
echo.
echo Si aparecieron los iconos en tu Escritorio, ya puedes cerrar esta ventana.
pause
