@echo off
chcp 65001 >nul
title AGY TRADING SYSTEM - PARAR TODOS OS 12 DESKS + RADAR + DASHBOARD
cd /d "C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot"
set PYTHONIOENCODING=utf-8

echo =================================================================
echo  [AGY TRADING] ENCERRANDO TODOS OS 12 DESKS, RADAR E O DASHBOARD...
echo =================================================================
echo.

python shutdown_desks.py

echo.
echo Todos os 12 Desks, Radar Whale e Dashboard foram finalizados com sucesso.
echo.
timeout /t 3 >nul
