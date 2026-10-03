@echo off
chcp 65001 >nul
title AGY TRADING SYSTEM - PAINEL DE CONTROLE (12 DESKS + RADAR WHALE)
cd /d "C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot"
set PYTHONIOENCODING=utf-8

cls
echo ===============================================================================
echo        AGY TRADING SYSTEM - CONTROLE DE DESKS (12 DESKS + RADAR WHALE)
echo ===============================================================================
echo  Desks Configurados:
echo   [Web]     Dashboard Server Web             (http://localhost:8080)
echo   [Desk 1]  Polymarket BTC 5m                (Modo REAL / LIVE)
echo   [Desk 2]  Polymarket SOL 5m                (Modo REAL / LIVE)
echo   [Desk 3]  Kalshi BTC 15m                   (Modo REAL / LIVE)
echo   [Desk 4]  Kalshi NatGas EIA Semanal        (Modo PAPER / API Real)
echo   [Desk 5]  Kalshi NatGas 15m                (Modo REAL / LIVE - EIA Shield)
echo   [Desk 6]  Yield Harvester e Theta          (Modo PAPER)
echo   [Desk 7]  Cross-Arb Macro Poly e Kalshi    (RADAR SCANNER)
echo   [Desk 8]  Polymarket ETH 5m                (Modo PAPER)
echo   [Desk 9]  Kalshi Gold 15m                  (Modo PAPER)
echo   [Desk 11] Kalshi SPX 500 15m Momentum      (Modo PAPER)
echo   [Desk 12] Weather METAR 14 Aeroportos      (Modo PAPER)
echo   [Radar]   Whale Liquidity Spike Monitor    (POLARIS WHALE FLOW)
echo ===============================================================================
echo  Selecione o modo de execucao:
echo.
echo   [1] Iniciar TUDO em Janelas Minimizadas + Abrir Dashboard Web (Recomendado)
echo   [2] Iniciar TUDO com Janelas Visiveis (Terminais abertos para ver logs)
echo   [3] Abrir Apenas o Dashboard Server (http://localhost:8080)
echo   [4] Parar / Encerrar Todos os Robos e Dashboard
echo   [0] Sair
echo ===============================================================================
set "OPCAO=1"
set /p "OPCAO=Digite o numero da opcao e pressione [Enter] (Padrao 1): "

if "%OPCAO%"=="1" goto MODO_MINIMIZADO
if "%OPCAO%"=="2" goto MODO_VISIVEL
if "%OPCAO%"=="3" goto APENAS_DASH
if "%OPCAO%"=="4" goto PARAR_TUDO
if "%OPCAO%"=="0" goto SAIR
goto MODO_MINIMIZADO

:MODO_MINIMIZADO
echo.
echo [1/13] Iniciando Dashboard Server em segundo plano...
start "AGY - Dashboard" /min cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u dashboard_server.py"

echo [2/13] Iniciando Desk 1 (Polymarket BTC 5m LIVE)...
start "AGY - Desk 1 BTC 5m Live" /min cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u live_trader_5m.py"

echo [3/13] Iniciando Desk 2 (Polymarket SOL 5m LIVE)...
start "AGY - Desk 2 SOL 5m Live" /min cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u sol_trader_5m.py"

echo [4/13] Iniciando Desk 3 (Kalshi BTC 15m LIVE)...
start "AGY - Desk 3 Kalshi BTC 15m Live" /min cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u kalshi_trader_15m.py"

echo [5/13] Iniciando Desk 4 (Kalshi NatGas EIA Semanal PAPER)...
start "AGY - Desk 4 NatGas EIA Paper" /min cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u kalshi_natgas_daemon.py"

echo [6/13] Iniciando Desk 5 (Kalshi NatGas 15m LIVE - EIA Shield)...
start "AGY - Desk 5 Kalshi NatGas 15m Live" /min cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u kalshi_natgas_trader_15m.py"

echo [7/13] Iniciando Desk 6: Yield Harvester e Theta PAPER...
start "AGY - Desk 6 Yield e Theta Paper" /min cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u desk6_yield_harvester.py"

echo [8/13] Iniciando Desk 7: Cross-Market Macro Arbitrageur...
start "AGY - Desk 7 Cross-Arb Scanner" /min cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u desk7_cross_arb.py"

echo [9/13] Iniciando Desk 8 (Polymarket ETH 5m PAPER)...
start "AGY - Desk 8 ETH 5m Paper" /min cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u eth_trader_5m.py"

echo [10/13] Iniciando Desk 9 (Kalshi Gold 15m PAPER)...
start "AGY - Desk 9 Gold 15m Paper" /min cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u kalshi_gold_trader_15m.py"

echo [11/13] Iniciando Desk 11: Kalshi SPX 500 15m Momentum e Sweeper PAPER...
start "AGY - Desk 11 SPX 15m Paper" /min cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u kalshi_spx_trader_15m.py"

echo [12/13] Iniciando Desk 12: Weather e METAR 14 Aeroportos PAPER...
start "AGY - Desk 12 Weather METAR Paper" /min cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u desk12_weather_metar.py"

echo [13/13] Iniciando Whale Liquidity Spike Monitor...
start "AGY - Whale Radar" /min cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u whale_flow_monitor.py"

echo.
echo ===============================================================================
echo  Todos os 12 desks, radar whale e o dashboard foram iniciados com sucesso!
echo  As janelas estao minimizadas na barra de tarefas.
echo  Abrindo o Dashboard no navegador (http://localhost:8080)...
echo ===============================================================================
timeout /t 2 >nul
start http://localhost:8080
timeout /t 3 >nul
exit

:MODO_VISIVEL
echo.
echo [1/13] Iniciando Dashboard Server (Janela Visivel)...
start "AGY - Dashboard" cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u dashboard_server.py"

echo [2/13] Iniciando Desk 1 (Polymarket BTC 5m LIVE)...
start "AGY - Desk 1 BTC 5m Live" cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u live_trader_5m.py"

echo [3/13] Iniciando Desk 2 (Polymarket SOL 5m LIVE)...
start "AGY - Desk 2 SOL 5m Live" cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u sol_trader_5m.py"

echo [4/13] Iniciando Desk 3 (Kalshi BTC 15m LIVE)...
start "AGY - Desk 3 Kalshi BTC 15m Live" cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u kalshi_trader_15m.py"

echo [5/13] Iniciando Desk 4 (Kalshi NatGas EIA Semanal PAPER)...
start "AGY - Desk 4 NatGas EIA Paper" cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u kalshi_natgas_daemon.py"

echo [6/13] Iniciando Desk 5 (Kalshi NatGas 15m LIVE - EIA Shield)...
start "AGY - Desk 5 Kalshi NatGas 15m Live" cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u kalshi_natgas_trader_15m.py"

echo [7/13] Iniciando Desk 6: Yield Harvester e Theta PAPER...
start "AGY - Desk 6 Yield e Theta Paper" cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u desk6_yield_harvester.py"

echo [8/13] Iniciando Desk 7: Cross-Market Macro Arbitrageur...
start "AGY - Desk 7 Cross-Arb Scanner" cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u desk7_cross_arb.py"

echo [9/13] Iniciando Desk 8 (Polymarket ETH 5m PAPER)...
start "AGY - Desk 8 ETH 5m Paper" cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u eth_trader_5m.py"

echo [10/13] Iniciando Desk 9 (Kalshi Gold 15m PAPER)...
start "AGY - Desk 9 Gold 15m Paper" cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u kalshi_gold_trader_15m.py"

echo [11/13] Iniciando Desk 11: Kalshi SPX 500 15m Momentum e Sweeper PAPER...
start "AGY - Desk 11 SPX 15m Paper" cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u kalshi_spx_trader_15m.py"

echo [12/13] Iniciando Desk 12: Weather e METAR 14 Aeroportos PAPER...
start "AGY - Desk 12 Weather METAR Paper" cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u desk12_weather_metar.py"

echo [13/13] Iniciando Whale Liquidity Spike Monitor...
start "AGY - Whale Radar" cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u whale_flow_monitor.py"

echo.
echo ===============================================================================
echo  Todos os 12 desks, radar whale e o dashboard foram iniciados com janelas ativas!
echo  Abrindo o Dashboard no navegador (http://localhost:8080)...
echo ===============================================================================
timeout /t 2 >nul
start http://localhost:8080
timeout /t 3 >nul
exit

:APENAS_DASH
echo.
echo Iniciando apenas o Dashboard Server...
start "AGY - Dashboard" cmd /k "cd /d C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot && chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python -u dashboard_server.py"
timeout /t 2 >nul
start http://localhost:8080
exit

:PARAR_TUDO
echo.
python shutdown_desks.py
echo.
echo Pressione qualquer tecla para sair...
pause >nul
exit

:SAIR
exit
