@echo off
chcp 65001 >nul
title AGY - Desk 5: Kalshi NatGas 15m LIVE (EIA Shock Shield)
cd /d "C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot"
set PYTHONIOENCODING=utf-8
color 0B

echo ===============================================================================
echo   AGY DESK 5: KALSHI NATURAL GAS 15-MINUTE ALGO TRADER (LIVE)
echo ===============================================================================
echo   Shard de Risco: Shard 2 (Commodities)
echo   Modo de Execucao: LIVE (API Oficial Kalshi RSA-PSS)
echo   Inovacao: Escudo de Choque EIA Calibrado via Databento NYMEX (53 Semanas)
echo   Deadband Rotina: 10.0 bps ($0.0040) ^| Deadband EIA (Quintas): 25.0 bps ($0.0080)
echo ===============================================================================
echo.
python -u kalshi_natgas_trader_15m.py
pause
