@echo off
cd /d "C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot"
start "AGY - Desk 1 (BTC 5m Live)" /min cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u live_trader_5m.py"
start "AGY - Desk 2 (SOL 5m Live)" /min cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u sol_trader_5m.py"
