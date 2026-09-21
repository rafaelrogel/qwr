@echo off
title Polymarket Algo Trader - Dashboard Launcher

:: Verifica se a porta 8080 está ouvindo
powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue)" >nul 2>&1
if %errorLevel% neq 0 (
    echo Iniciando o servidor do Polymarket Dashboard em segundo plano...
    start /B pythonw "C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot\dashboard_server.py"
    timeout /t 2 /nobreak >nul
)

:: Abre o navegador padrao direto no Dashboard
echo Abrindo o Dashboard no seu navegador...
start http://localhost:8080
exit
