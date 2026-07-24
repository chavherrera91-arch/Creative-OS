@echo off
title Minero quantos - varios mercados
cd /d "%~dp0"
set "VENV=%LOCALAPPDATA%\quantos\.venv\Scripts\python.exe"
if not exist "%VENV%" set "VENV=python"
echo ==================================================
echo    Minero quantos - BTC + ETH + EUR/USD juntos
echo ==================================================
echo.
echo Mina los 3 mercados en cada ronda.
echo Una estrategia que pase en 2+ mercados es un DIAMANTE.
echo El oro y los diamantes aparecen en la app, seccion Boveda.
echo Deja esta ventana abierta (puedes minimizarla).
echo Cierra la ventana para detenerlo.
echo.
"%VENV%" -m quantos.mining.run --markets "BTC/USDT:crypto,ETH/USDT:crypto,EUR/USD:forex"
pause
