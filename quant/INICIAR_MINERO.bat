@echo off
chcp 65001 >nul
title Minero quantos
cd /d "%~dp0"
set "VENV=%LOCALAPPDATA%\quantos\.venv\Scripts\python.exe"
if not exist "%VENV%" set "VENV=python"
echo ============================================
echo   Minero quantos — buscando estrategias
echo ============================================
echo.
echo Deja esta ventana abierta (puedes MINIMIZARLA) mientras no estas.
echo El oro que encuentre aparece en la app, seccion "Bóveda de oro".
echo Cierra la ventana para detenerlo.
echo.
"%VENV%" -m quantos.mining.run --symbol BTC/USDT
pause
