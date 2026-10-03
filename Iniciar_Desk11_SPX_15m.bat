@echo off
chcp 65001 >nul
title AGY - Desk 11: Kalshi SPX 15m Momentum (Databento Calibrated)
cd /d "C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot"
set PYTHONIOENCODING=utf-8
color 0E

echo ===============================================================================
echo   AGY DESK 11: KALSHI S^&P 500 15-MINUTE MOMENTUM TRADER
echo ===============================================================================
echo   Modo de Execucao: PAPER (API Oficial Kalshi)
echo   Calibracao Databento: 6.691 Velas CME E-mini S^&P 500
echo   Delta Minimo: 4.00 pts ^| Sweet Spot de Decisao: 450s (50%% da vela)
echo ===============================================================================
echo.
python -u kalshi_spx_trader_15m.py
pause
