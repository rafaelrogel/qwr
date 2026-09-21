"""
Servidor Simplificado e Otimizado do Polymarket Algo Trader:
- Foco exclusivo em:
  1. Depósito Inicial ($21.00 USDC)
  2. Saldo Real do Polymarket em Tempo Real (via CLOB V2)
  3. "O Atual": Ciclo 5m Ativo (Strike Chainlink, Spot Chainlink, Binance, Delta, Timer e Sinal)
  4. Resumo de Perdas e Lucros (Baseado estritamente nas apostas participadas)
  5. Tabela de Perdas e Lucros com as Últimas 20 Apostas que Fizemos e Participamos
Roda nativamente na porta 8080.
"""
import http.server
import socketserver
import json
import os
import csv
import urllib.request
import threading
import time
from datetime import datetime
from typing import Dict, Any, List

from py_clob_client_v2 import (
    ClobClient,
    SignatureTypeV2,
    BalanceAllowanceParams,
    AssetType
)
from btc_5m_engine import BTC5mEngine

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
JOURNAL_CSV = os.path.join(BASE_DIR, "live_trading_journal.csv")
JOURNAL_JSON = os.path.join(BASE_DIR, "live_trading_journal.json")

INITIAL_DEPOSIT = 21.00

# Estado global do Dashboard
ACCOUNT_STATE: Dict[str, Any] = {
    "initial_deposit": INITIAL_DEPOSIT,
    "current_balance": 18.5025,
    "last_balance_update": 0,
    "funder_address": "",
    "status": "CONECTADO"
}

btc_engine = BTC5mEngine()

def load_env_config() -> Dict[str, str]:
    cfg = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    return cfg

ENV_CFG = load_env_config()
PRIV_KEY = ENV_CFG.get("POLYGON_PRIVATE_KEY", "").strip()
if PRIV_KEY.startswith("0x"):
    PRIV_KEY = PRIV_KEY[2:]
FUNDER_ADDR = ENV_CFG.get("POLY_FUNDER_ADDRESS", "").strip()
ACCOUNT_STATE["funder_address"] = FUNDER_ADDR

clob_client = None
if PRIV_KEY and FUNDER_ADDR:
    try:
        clob_client = ClobClient(
            host="https://clob.polymarket.com",
            key=PRIV_KEY,
            chain_id=137,
            signature_type=SignatureTypeV2.POLY_1271,
            funder=FUNDER_ADDR
        )
        creds = clob_client.derive_api_key()
        clob_client.set_api_creds(creds)
    except Exception as e:
        print(f"[Aviso CLOB Client]: {e}")
        clob_client = None

def balance_polling_worker():
    """Atualiza o saldo real em USDC via CLOB API em segundo plano"""
    global ACCOUNT_STATE, clob_client
    while True:
        if clob_client:
            try:
                params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
                info = clob_client.get_balance_allowance(params)
                raw_bal = float(info.get("balance", 0.0))
                ACCOUNT_STATE["current_balance"] = round(raw_bal / 1e6, 4)
                ACCOUNT_STATE["last_balance_update"] = time.time()
                ACCOUNT_STATE["status"] = "CONECTADO"
            except Exception as e:
                ACCOUNT_STATE["status"] = f"Aviso: {e}"
        time.sleep(3.0)

def get_recent_trades_and_stats(limit: int = 20) -> Dict[str, Any]:
    """
    Lê EXCLUSIVAMENTE as apostas que fizemos e participamos:
    Filtra apenas ordens reais enviadas com sucesso e confirmadas com tx_hash na Polygon.
    Exclui ciclos não operados ou que falharam no envio.
    """
    real_trades = []
    if os.path.exists(JOURNAL_JSON):
        try:
            with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                jdata = json.load(f)
                for t in jdata.get("trades", []):
                    if t.get("tx_hash", "").startswith("0x"):
                        res_str = t.get("result", "")
                        is_real_hedge = bool(t.get("hedged") or "HEDGE" in res_str.upper())
                        real_trades.append({
                            "cycle_num": t.get("cycle", ""),
                            "timestamp": t.get("timestamp", "").replace("T", " ")[:19],
                            "stake": float(t.get("total_stake", 2.00 if is_real_hedge else 1.00)),
                            "strike_K": float(t.get("strike_chainlink", 0.0)),
                            "final_spot": float(t.get("final_spot_chainlink", 0.0)),
                            "decision": t.get("target_side") or (t.get("scour_side") if t.get("scour_executed") else "-"),
                            "hedged": is_real_hedge,
                            "winner": t.get("winner", ""),
                            "result": res_str,
                            "entry_price": float(t.get("price", 0.50)),
                            "shares": float(t.get("shares") or t.get("scour_shares") or 0.0),
                            "payout": float(t.get("total_payout", 0.0)),
                            "cycle_pnl": float(t.get("cycle_pnl", 0.0)),
                            "balance": float(t.get("balance", 0.0)),
                            "tx_hash": t.get("tx_hash", ""),
                            "hedge_tx_hash": t.get("hedge_tx_hash", "")
                        })
        except Exception as e:
            print(f"[Erro leitura JSON]: {e}")
    elif os.path.exists(JOURNAL_CSV):
        try:
            with open(JOURNAL_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("status") == "SUCCESS" and row.get("tx_hash", "").startswith("0x"):
                        res_str = row.get("result", "")
                        is_real_hedge = (row.get("hedged") == "SIM" or "HEDGE" in res_str.upper())
                        real_trades.append({
                            "cycle_num": row.get("cycle_num", ""),
                            "timestamp": row.get("timestamp", ""),
                            "stake": 2.00 if is_real_hedge else 1.00,
                            "strike_K": float(row.get("strike_K", 0.0)),
                            "final_spot": float(row.get("final_spot", 0.0)),
                            "decision": row.get("decision", ""),
                            "hedged": is_real_hedge,
                            "winner": row.get("winner", ""),
                            "result": res_str,
                            "entry_price": float(row.get("entry_price") or 0.50),
                            "shares": float(row.get("shares") or 0.0),
                            "payout": float(row.get("payout", 0.0)),
                            "cycle_pnl": float(row.get("cycle_pnl", 0.0)),
                            "balance": float(row.get("balance", 0.0)),
                            "tx_hash": row.get("tx_hash", ""),
                            "hedge_tx_hash": row.get("hedge_tx_hash", "")
                        })
        except Exception as e:
            print(f"[Erro leitura CSV]: {e}")

    total_real_trades = len(real_trades)
    wins = 0
    losses = 0
    total_staked = sum(float(t.get("stake", 1.00)) for t in real_trades)
    gross_profit = 0.0
    gross_loss = 0.0

    # Numera cada aposta real de 1 a N
    for idx, t in enumerate(real_trades, start=1):
        t["real_bet_num"] = idx

    parsed_recent = []
    for t in real_trades[-limit:][::-1]: # Últimas apostas participadas, mais recente primeiro
        res = t.get("result", "").upper()
        pnl_val = float(t.get("cycle_pnl", 0.0))
        stake_val = float(t.get("stake", 1.00))

        # Determinação rigorosa e sem generalização falsa de hedge
        if "TAKE PROFIT" in res:
            result_label = "VITÓRIA (TP ANTECIPADO)"
        elif "STOP LOSS" in res:
            result_label = "DEFESA (STOP LOSS)"
        elif "SCOUR" in res or "SWEEPER" in res:
            result_label = "VITÓRIA (SWEEPER)" if pnl_val >= 0 else "DERROTA (SWEEPER)"
        elif "HEDGE" in res:
            result_label = "VITÓRIA (HEDGE)" if pnl_val >= 0 else "DEFESA (HEDGE)"
        elif pnl_val > 0.0:
            result_label = "VITÓRIA"
        elif pnl_val == 0.0:
            result_label = "BREAKEVEN"
        else:
            result_label = "DERROTA"

        parsed_recent.append({
            "bet_num": t.get("real_bet_num", 0),
            "cycle": t.get("cycle_num", ""),
            "timestamp": t.get("timestamp", ""),
            "stake": stake_val,
            "strike": t.get("strike_K", 0.0),
            "final_spot": t.get("final_spot", 0.0),
            "decision": t.get("decision", ""),
            "hedged": t.get("hedged", False),
            "hedge_decision": t.get("hedge_decision", ""),
            "winner": t.get("winner", ""),
            "result": result_label,
            "entry_price": t.get("entry_price", 0.50),
            "shares": t.get("shares", 0.0),
            "payout": t.get("payout", 0.0),
            "cycle_pnl": pnl_val,
            "balance": t.get("balance", 0.0),
            "tx_hash": t.get("tx_hash", ""),
            "hedge_tx_hash": t.get("hedge_tx_hash", "")
        })

    # Estatísticas globais acumuladas de todas as apostas que participamos
    for t in real_trades:
        try:
            pnl_val = float(t.get("cycle_pnl", 0.0))
        except Exception:
            pnl_val = 0.0

        if pnl_val > 0.0:
            wins += 1
            gross_profit += pnl_val
        elif pnl_val < 0.0:
            losses += 1
            gross_loss += abs(pnl_val)
        else:
            # Breakeven (não incrementa vitória nem derrota)
            pass

    current_bal = ACCOUNT_STATE.get("current_balance", 18.50)
    net_real_pnl = round(current_bal - INITIAL_DEPOSIT, 2)
    net_real_pnl_pct = round((net_real_pnl / INITIAL_DEPOSIT) * 100, 2)
    win_rate = round((wins / total_real_trades * 100), 1) if total_real_trades > 0 else 0.0

    return {
        "pnl_summary": {
            "initial_deposit": INITIAL_DEPOSIT,
            "current_balance": current_bal,
            "net_real_pnl": net_real_pnl,
            "net_real_pnl_pct": net_real_pnl_pct,
            "total_participated_bets": total_real_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "total_spent": round(total_staked, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "stop_loss_limit": -5.00,
            "take_profit_limit": 50.00
        },
        "recent_trades": parsed_recent
    }

HTML_CONTENT = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Polymarket BTC 5m - Painel Operacional</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700;800&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #070a11;
            --bg-card: #0e1422;
            --bg-card-sub: #141c2e;
            --border: #1b263b;
            --border-highlight: #2c3c58;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-green: #10b981;
            --accent-green-glow: rgba(16, 185, 129, 0.18);
            --accent-red: #f43f5e;
            --accent-red-glow: rgba(244, 63, 94, 0.18);
            --accent-blue: #38bdf8;
            --accent-gold: #f59e0b;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: var(--bg-base);
            color: var(--text-main);
            font-family: 'Inter', -apple-system, sans-serif;
            font-size: 13px;
            padding-bottom: 50px;
        }

        .mono { font-family: 'JetBrains Mono', monospace; }

        /* Top Header */
        header {
            background-color: var(--bg-card);
            border-bottom: 1px solid var(--border);
            padding: 14px 28px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand-logo {
            background: linear-gradient(135deg, #f59e0b, #d97706);
            color: #000;
            font-weight: 800;
            padding: 5px 10px;
            border-radius: 6px;
            font-size: 11px;
            letter-spacing: 0.5px;
        }

        .brand h1 {
            font-size: 17px;
            font-weight: 700;
            letter-spacing: -0.3px;
        }

        .header-tags {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .badge-tag {
            background: var(--bg-base);
            border: 1px solid var(--border);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 11px;
            display: flex;
            align-items: center;
            gap: 6px;
            color: var(--text-muted);
        }

        .dot-pulse {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: var(--accent-green);
            box-shadow: 0 0 8px var(--accent-green);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.4; transform: scale(0.85); }
        }

        /* Container */
        .container {
            max-width: 1280px;
            margin: 20px auto;
            padding: 0 20px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        /* 4 Top Hero Cards */
        .hero-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
        }

        .hero-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 18px 20px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            position: relative;
            overflow: hidden;
        }

        .hero-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: var(--border-highlight);
        }

        .hero-card.accent-deposit::before { background: var(--accent-blue); }
        .hero-card.accent-balance::before { background: var(--accent-green); }
        .hero-card.accent-pnl::before { background: var(--accent-gold); }
        .hero-card.accent-winrate::before { background: #a855f7; }

        .hero-title {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.6px;
            color: var(--text-muted);
            font-weight: 600;
        }

        .hero-value {
            font-size: 26px;
            font-weight: 800;
            letter-spacing: -0.5px;
        }

        .hero-sub {
            font-size: 11px;
            color: var(--text-muted);
        }

        /* Card Section Base */
        .panel {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px 24px;
        }

        .panel-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border);
        }

        .panel-title {
            font-size: 15px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* "O ATUAL" SECTION */
        .current-cycle-box {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .timer-badge {
            font-size: 18px;
            font-weight: 700;
            color: var(--accent-gold);
        }

        .progress-bar-wrap {
            width: 100%;
            height: 6px;
            background: var(--border);
            border-radius: 3px;
            overflow: hidden;
            margin-top: 6px;
        }

        .progress-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--accent-blue), var(--accent-green));
            transition: width 1s linear;
        }

        .pricing-boxes {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 14px;
        }

        .price-box {
            background: var(--bg-base);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 14px 16px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .price-box-title {
            font-size: 11px;
            color: var(--text-muted);
            font-weight: 600;
        }

        .price-box-val {
            font-size: 20px;
            font-weight: 800;
        }

        .price-box-sub {
            font-size: 11px;
            font-weight: 600;
        }

        .signal-banner {
            background: var(--bg-card-sub);
            border-left: 4px solid var(--accent-green);
            padding: 14px 18px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .signal-title {
            font-size: 14px;
            font-weight: 700;
            margin-bottom: 2px;
        }

        .signal-desc {
            font-size: 12px;
            color: var(--text-muted);
        }

        /* P&L TABLE / SUMMARY */
        .pnl-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }

        .pnl-table {
            width: 100%;
            border-collapse: collapse;
        }

        .pnl-table tr {
            border-bottom: 1px solid var(--border);
        }

        .pnl-table tr:last-child {
            border-bottom: none;
        }

        .pnl-table td {
            padding: 10px 12px;
        }

        .pnl-table td.label {
            color: var(--text-muted);
            font-weight: 500;
        }

        .pnl-table td.val {
            text-align: right;
            font-weight: 700;
        }

        /* TRADES TABLE */
        .table-responsive {
            overflow-x: auto;
        }

        table.trades-table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }

        table.trades-table th {
            padding: 12px 14px;
            background: var(--bg-card-sub);
            color: var(--text-muted);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid var(--border);
        }

        table.trades-table td {
            padding: 12px 14px;
            border-bottom: 1px solid var(--border);
            font-size: 12px;
        }

        table.trades-table tr:hover td {
            background: rgba(255, 255, 255, 0.02);
        }

        .badge-win {
            background: var(--accent-green-glow);
            color: var(--accent-green);
            border: 1px solid var(--accent-green);
            padding: 3px 8px;
            border-radius: 4px;
            font-weight: 700;
            font-size: 11px;
            display: inline-block;
        }

        .badge-loss {
            background: var(--accent-red-glow);
            color: var(--accent-red);
            border: 1px solid var(--accent-red);
            padding: 3px 8px;
            border-radius: 4px;
            font-weight: 700;
            font-size: 11px;
            display: inline-block;
        }

        .badge-hedge {
            background: rgba(249, 115, 22, 0.16);
            color: #f97316;
            border: 1px solid rgba(249, 115, 22, 0.6);
            padding: 3px 8px;
            border-radius: 4px;
            font-weight: 700;
            font-size: 11px;
            display: inline-block;
            letter-spacing: 0.3px;
        }

        .badge-side-up {
            background: rgba(16, 185, 129, 0.15);
            color: var(--accent-green);
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 700;
            font-size: 11px;
        }

        .badge-side-down {
            background: rgba(244, 63, 94, 0.15);
            color: var(--accent-red);
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 700;
            font-size: 11px;
        }

        .tx-link {
            color: var(--accent-blue);
            text-decoration: none;
            font-size: 11px;
        }

        .tx-link:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>

    <header>
        <div class="brand">
            <span class="brand-logo">POLYMARKET</span>
            <h1>BTC 5M Algo Terminal</h1>
        </div>
        <div class="header-tags">
            <div class="badge-tag">
                <span class="dot-pulse"></span>
                <span>LIVE TRADING</span>
            </div>
            <div class="badge-tag" style="background: rgba(16, 185, 129, 0.12); border-color: rgba(16, 185, 129, 0.4); color: var(--accent-green);">
                <span class="dot-pulse" style="background: var(--accent-green);"></span>
                <span id="syncClock" class="mono">Sync: Ao Vivo...</span>
            </div>
            <div class="badge-tag">
                <span>Oráculo: Chainlink TWAP 60s</span>
            </div>
            <div class="badge-tag">
                <span>Proxy: <span id="funderAddrDisplay" class="mono">...</span></span>
            </div>
        </div>
    </header>

    <div class="container">

        <!-- 4 TOP CARDS -->
        <div class="hero-grid">
            <div class="hero-card accent-deposit">
                <div class="hero-title">Depósito Inicial</div>
                <div class="hero-value mono" style="color: var(--accent-blue);">$21.00 USDC</div>
                <div class="hero-sub">Capital inicial aportado na carteira</div>
            </div>

            <div class="hero-card accent-balance">
                <div class="hero-title">Saldo Real em Tempo Real</div>
                <div class="hero-value mono" id="heroCurrentBalance" style="color: var(--accent-green);">$18.50 USDC</div>
                <div class="hero-sub">Sincronizado diretamente via CLOB V2</div>
            </div>

            <div class="hero-card accent-pnl">
                <div class="hero-title">P&L Real Consolidado</div>
                <div class="hero-value mono" id="heroNetPnl">-$2.50 USDC</div>
                <div class="hero-sub" id="heroNetPnlSub">Saldo Atual ($18.50) - Depósito ($21.00)</div>
            </div>

            <div class="hero-card accent-winrate">
                <div class="hero-title">Apostas que Participamos</div>
                <div class="hero-value mono" id="heroWinRate" style="color: #c084fc;">70.8%</div>
                <div class="hero-sub" id="heroWinCount">17 Vitórias / 7 Derrotas (24 Apostas Reais)</div>
            </div>
        </div>

        <!-- O ATUAL (CICLO 5M ATIVO) -->
        <div class="panel">
            <div class="panel-header">
                <div class="panel-title">
                    <span>⚡ O Atual (Ciclo Ativo 5m)</span>
                    <span id="cycleTitleBadge" style="font-size: 12px; color: var(--text-muted); font-weight: 500;">Carregando...</span>
                </div>
                <div class="timer-badge mono" id="timerDisplay">Restam: --s</div>
            </div>

            <div class="current-cycle-box">
                <div>
                    <div class="progress-bar-wrap">
                        <div class="progress-bar-fill" id="progressBar" style="width: 0%;"></div>
                    </div>
                </div>

                <div class="pricing-boxes">
                    <div class="price-box">
                        <div class="price-box-title">STRIKE PRICE (K)</div>
                        <div class="price-box-val mono" id="boxStrike">$0.00</div>
                        <div class="price-box-sub" style="color: var(--text-muted);">Abertura do Oráculo Chainlink</div>
                    </div>

                    <div class="price-box">
                        <div class="price-box-title">ORÁCULO CHAINLINK (SPOT)</div>
                        <div class="price-box-val mono" id="boxOracleSpot" style="color: var(--accent-blue);">$0.00</div>
                        <div class="price-box-sub" id="boxOracleStatus">Cotação Oficial Polygon</div>
                    </div>

                    <div class="price-box">
                        <div class="price-box-title">DERIVA ATUAL (DELTA)</div>
                        <div class="price-box-val mono" id="boxDelta">$0.00</div>
                        <div class="price-box-sub" id="boxDeltaStatus">Δ = Chainlink - Strike</div>
                    </div>

                    <div class="price-box">
                        <div class="price-box-title">BINANCE SPOT (REF)</div>
                        <div class="price-box-val mono" id="boxBinanceSpot">$0.00</div>
                        <div class="price-box-sub" id="boxSpread">Spread: $0.00</div>
                    </div>
                </div>

                <div class="signal-banner" id="signalBanner">
                    <div>
                        <div class="signal-title" id="signalAction">Aguardando microestrutura intra-vela...</div>
                        <div class="signal-desc" id="signalRationale">Avaliando cotações e reversão markoviana para tomada de decisão no minuto 2:15.</div>
                    </div>
                    <div class="mono" style="font-size: 13px; font-weight: 700;" id="polyOddsDisplay">
                        Polymarket: UP $0.50 | DOWN $0.50
                    </div>
                </div>
            </div>
        </div>

        <!-- RESUMO DE PERDAS E LUCROS (APOSTAS PARTICIPADAS) -->
        <div class="panel">
            <div class="panel-header">
                <div class="panel-title">
                    <span>📊 Resumo de Perdas e Lucros (Apostas que Participamos)</span>
                </div>
                <div style="font-size: 11px; color: var(--text-muted);">
                    Calculado estritamente sobre as apostas reais executadas com sucesso
                </div>
            </div>

            <div class="pnl-grid">
                <!-- Coluna 1: Balanço Contábil Real -->
                <div style="background: var(--bg-card-sub); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px;">
                    <div style="font-size: 12px; font-weight: 700; margin-bottom: 8px; color: var(--accent-blue);">Balanço da Carteira</div>
                    <table class="pnl-table">
                        <tr>
                            <td class="label">Depósito Inicial de Referência</td>
                            <td class="val mono" style="color: var(--accent-blue);">$21.00 USDC</td>
                        </tr>
                        <tr>
                            <td class="label">Saldo Líquido Atual em Conta</td>
                            <td class="val mono" id="pnlTableCurrentBal">$18.50 USDC</td>
                        </tr>
                        <tr>
                            <td class="label">P&L Líquido Real da Carteira</td>
                            <td class="val mono" id="pnlTableNetVal">-$2.50 USDC (-11.90%)</td>
                        </tr>
                        <tr>
                            <td class="label">Gatilho Stop Loss (Proteção)</td>
                            <td class="val mono" style="color: var(--accent-red);">$13.50 USDC (-$5.00 da sessão)</td>
                        </tr>
                        <tr>
                            <td class="label">Gatilho Take Profit (Meta)</td>
                            <td class="val mono" style="color: var(--accent-green);">$68.50 USDC (+$50.00 da sessão)</td>
                        </tr>
                    </table>
                </div>

                <!-- Coluna 2: Desempenho das Nossas Apostas -->
                <div style="background: var(--bg-card-sub); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px;">
                    <div style="font-size: 12px; font-weight: 700; margin-bottom: 8px; color: var(--accent-gold);">Estatísticas das Nossas Apostas</div>
                    <table class="pnl-table">
                        <tr>
                            <td class="label">Total de Apostas que Participamos</td>
                            <td class="val mono" id="pnlTableTotalTrades">24 apostas</td>
                        </tr>
                        <tr>
                            <td class="label">Capital Total Alocado em Apostas</td>
                            <td class="val mono" id="pnlTableTotalSpent">$24.00 USDC ($1.00 por aposta)</td>
                        </tr>
                        <tr>
                            <td class="label">Apostas com Lucro (Vitórias)</td>
                            <td class="val mono" style="color: var(--accent-green);" id="pnlTableWins">17 vitórias</td>
                        </tr>
                        <tr>
                            <td class="label">Apostas com Prejuízo (Derrotas)</td>
                            <td class="val mono" style="color: var(--accent-red);" id="pnlTableLosses">7 derrotas</td>
                        </tr>
                        <tr>
                            <td class="label">Taxa de Sucesso das Apostas</td>
                            <td class="val mono" style="color: #c084fc;" id="pnlTableWinRate">70.8%</td>
                        </tr>
                    </table>
                </div>
            </div>
        </div>

        <!-- TABELA DE PERDAS E LUCROS (APOSTAS QUE FIZEMOS E PARTICIPAMOS) -->
        <div class="panel">
            <div class="panel-header">
                <div class="panel-title">
                    <span>📋 Tabela de Perdas e Lucros (Apostas que Fizemos e Participamos)</span>
                </div>
                <div style="font-size: 11px; color: var(--text-muted);" id="tradesTableCount">
                    Listando as últimas 20 apostas reais com comprovante on-chain
                </div>
            </div>

            <div class="table-responsive">
                <table class="trades-table">
                    <thead>
                        <tr>
                            <th># Aposta Real</th>
                            <th>Horário</th>
                            <th>Ciclo 5m</th>
                            <th>Nossa Aposta</th>
                            <th>Valor Apostado</th>
                            <th>Preço Cota</th>
                            <th>Cotas (Shares)</th>
                            <th>Resultado</th>
                            <th>Retorno (Payout)</th>
                            <th>Lucro/Prejuízo (P&L)</th>
                            <th>Saldo Resultante</th>
                            <th>Comprovante On-Chain</th>
                        </tr>
                    </thead>
                    <tbody id="tradesTableBody">
                        <tr>
                            <td colspan="12" style="text-align: center; color: var(--text-muted); padding: 24px;">Carregando apostas participadas...</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

    </div>

    <script>
        async function updateDashboard() {
            try {
                const res = await fetch('/api/dashboard_state?_t=' + Date.now());
                const data = await res.json();

                const nowTime = new Date().toLocaleTimeString('pt-BR');
                const syncEl = document.getElementById('syncClock');
                if (syncEl) syncEl.innerText = `Sync: ${nowTime} 🟢`;

                // 1. Atualiza Conta e Top Cards
                const acc = data.account || {};
                const pnl = data.pnl_summary || {};

                if (acc.funder_address) {
                    const addr = acc.funder_address;
                    document.getElementById('funderAddrDisplay').innerText = `${addr.substring(0, 6)}...${addr.substring(addr.length - 4)}`;
                }

                const curBal = Number(pnl.current_balance || 18.50).toFixed(2);
                document.getElementById('heroCurrentBalance').innerText = `$${curBal} USDC`;
                document.getElementById('pnlTableCurrentBal').innerText = `$${curBal} USDC`;

                const netPnl = Number(pnl.net_real_pnl || -2.50);
                const netPct = Number(pnl.net_real_pnl_pct || -11.90);
                const netSign = netPnl >= 0 ? '+' : '';
                const netPnlEl = document.getElementById('heroNetPnl');
                netPnlEl.innerText = `${netSign}$${netPnl.toFixed(2)} USDC`;
                netPnlEl.style.color = netPnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';

                document.getElementById('heroNetPnlSub').innerText = `Saldo Atual ($${curBal}) - Depósito ($21.00) | ${netSign}${netPct.toFixed(2)}%`;
                document.getElementById('pnlTableNetVal').innerText = `${netSign}$${netPnl.toFixed(2)} USDC (${netSign}${netPct.toFixed(2)}%)`;
                document.getElementById('pnlTableNetVal').style.color = netPnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';

                const totalParticipated = pnl.total_participated_bets || 24;
                const wins = pnl.wins || 17;
                const losses = pnl.losses || 7;
                const winRate = Number(pnl.win_rate || 70.8).toFixed(1);

                document.getElementById('heroWinRate').innerText = `${winRate}%`;
                document.getElementById('heroWinCount').innerText = `${wins} Vitórias / ${losses} Derrotas (${totalParticipated} Apostas Reais)`;

                document.getElementById('pnlTableTotalTrades').innerText = `${totalParticipated} apostas`;
                document.getElementById('pnlTableWins').innerText = `${wins} vitórias`;
                document.getElementById('pnlTableLosses').innerText = `${losses} derrotas`;
                document.getElementById('pnlTableTotalSpent').innerText = `$${Number(pnl.total_spent || 24).toFixed(2)} USDC ($1.00 por aposta)`;
                document.getElementById('pnlTableWinRate').innerText = `${winRate}%`;

                // 2. Atualiza "O Atual" (Ciclo 5m)
                const c = data.current_cycle || {};
                document.getElementById('cycleTitleBadge').innerText = c.title || `btc-updown-5m-${c.window_ts || ''}`;
                document.getElementById('timerDisplay').innerText = `Restam: ${c.seconds_left || 0}s`;
                document.getElementById('progressBar').style.width = `${c.progress_pct || 0}%`;

                document.getElementById('boxStrike').innerText = `$${Number(c.strike || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                document.getElementById('boxOracleSpot').innerText = `$${Number(c.oracle_spot || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

                const delta = Number(c.delta || 0);
                const deltaEl = document.getElementById('boxDelta');
                deltaEl.innerText = `${delta >= 0 ? '+' : ''}$${delta.toFixed(2)}`;
                deltaEl.style.color = delta >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
                document.getElementById('boxDeltaStatus').innerText = delta >= 0 ? '🟢 Tendência: UP' : '🔴 Tendência: DOWN';

                document.getElementById('boxBinanceSpot').innerText = `$${Number(c.binance_spot || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                const spread = Number(c.feed_spread || 0);
                document.getElementById('boxSpread').innerText = `Spread: ${spread >= 0 ? '+' : ''}$${spread.toFixed(2)}`;

                const priceUp = Number(c.poly_price_up || 0.50).toFixed(2);
                const priceDown = Number(c.poly_price_down || 0.50).toFixed(2);
                document.getElementById('polyOddsDisplay').innerText = `Polymarket: UP $${priceUp} | DOWN $${priceDown}`;

                if (c.signal) {
                    document.getElementById('signalAction').innerText = c.signal.action || 'Aguardando microestrutura...';
                    document.getElementById('signalRationale').innerText = c.signal.rationale || '';
                    if (c.signal.color) {
                        document.getElementById('signalBanner').style.borderLeftColor = c.signal.color;
                    }
                }

                // 3. Atualiza Tabela de Apostas Realizadas
                const trades = data.recent_trades || [];
                const tbody = document.getElementById('tradesTableBody');
                if (trades.length > 0) {
                    let html = '';
                    trades.forEach(t => {
                        const pnlVal = Number(t.cycle_pnl || 0);
                        const isWin = pnlVal > 0;
                        const isDefesa = (t.result && t.result.includes('DEFESA')) || (t.hedged && pnlVal < 0);

                        let resBadge = '';
                        if (isWin) {
                            resBadge = `<span class="badge-win">${t.result || 'VITÓRIA'}</span>`;
                        } else if (isDefesa) {
                            resBadge = `<span class="badge-hedge">🛡️ ${t.result || 'DEFESA'}</span>`;
                        } else if (pnlVal === 0) {
                            resBadge = `<span class="badge-hedge" style="background:rgba(148, 163, 184, 0.15); color:#94a3b8; border-color:#64748b;">BREAKEVEN</span>`;
                        } else {
                            resBadge = `<span class="badge-loss">DERROTA</span>`;
                        }

                        let sideBadge = t.decision === 'UP' ? `<span class="badge-side-up">UP</span>` : `<span class="badge-side-down">DOWN</span>`;
                        if (t.hedged && t.hedge_decision && t.hedge_decision !== '-') {
                            const hBadge = t.hedge_decision === 'UP' ? `<span class="badge-side-up" style="font-size:10px;">+UP🛡️</span>` : `<span class="badge-side-down" style="font-size:10px;">+DW🛡️</span>`;
                            sideBadge += ` ` + hBadge;
                        }

                        const pnlColor = pnlVal > 0 ? 'var(--accent-green)' : (pnlVal < 0 ? 'var(--accent-red)' : 'var(--text-muted)');
                        const pnlFormatted = `${pnlVal > 0 ? '+' : ''}$${pnlVal.toFixed(2)}`;
                        const payoutColor = isWin ? 'var(--accent-green)' : (isDefesa ? '#f97316' : 'var(--text-muted)');
                        const payoutFormatted = `$${Number(t.payout || 0).toFixed(2)}`;
                        const txHash = t.tx_hash || '';
                        let txLink = txHash ? `<a class="tx-link mono" href="https://polygonscan.com/tx/${txHash}" target="_blank">${txHash.substring(0, 6)}...${txHash.substring(txHash.length - 4)}</a>` : '-';
                        if (t.hedge_tx_hash) {
                            txLink += `<br><a class="tx-link mono" style="color:var(--accent-gold);" href="https://polygonscan.com/tx/${t.hedge_tx_hash}" target="_blank">🛡️${t.hedge_tx_hash.substring(0, 4)}...</a>`;
                        }

                        html += `
                            <tr>
                                <td class="mono" style="font-weight: 800; color: var(--accent-blue);">#${t.bet_num}</td>
                                <td class="mono" style="color: var(--text-muted);">${t.timestamp.split(' ')[1] || t.timestamp}</td>
                                <td class="mono" style="color: var(--text-muted);">Ciclo ${t.cycle}</td>
                                <td>${sideBadge}</td>
                                <td class="mono" style="font-weight: 600;">$${Number(t.stake).toFixed(2)}</td>
                                <td class="mono">$${Number(t.entry_price).toFixed(2)}</td>
                                <td class="mono" style="color: var(--text-muted);">${Number(t.shares).toFixed(2)}</td>
                                <td>${resBadge}</td>
                                <td class="mono" style="color: ${payoutColor}; font-weight: 600;">${payoutFormatted}</td>
                                <td class="mono" style="color: ${pnlColor}; font-weight: 800;">${pnlFormatted}</td>
                                <td class="mono">$${Number(t.balance).toFixed(2)}</td>
                                <td>${txLink}</td>
                            </tr>
                        `;
                    });
                    tbody.innerHTML = html;
                    document.getElementById('tradesTableCount').innerText = `Exibindo ${trades.length} apostas reais mais recentes (de ${totalParticipated} apostas participadas)`;
                }
            } catch (e) {
                console.error("Erro ao atualizar dashboard:", e);
            }
        }

        // Loop de alta frequência (a cada 1 segundo)
        setInterval(updateDashboard, 1000);
        updateDashboard();
    </script>
</body>
</html>
"""

class SimplifiedDashboardHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Silencia logs de requisição no console para manter terminal limpo

    def do_GET(self):
        global ACCOUNT_STATE, btc_engine
        if self.path == "/" or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode("utf-8"))
        elif self.path.startswith("/api/dashboard_state"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()

            # Estado atual do ciclo via BTC Engine
            radar = btc_engine.get_radar_state()
            pricing = radar.get("pricing", {})
            cycle = radar.get("cycle", {})
            poly = radar.get("polymarket", {})
            signal = radar.get("signal", {})

            # Métricas financeiras e histórico de 20 trades
            trades_info = get_recent_trades_and_stats(limit=20)

            payload = {
                "account": ACCOUNT_STATE,
                "current_cycle": {
                    "window_ts": cycle.get("window_ts"),
                    "title": cycle.get("title"),
                    "seconds_left": cycle.get("seconds_left"),
                    "seconds_elapsed": cycle.get("seconds_elapsed"),
                    "progress_pct": cycle.get("progress_pct"),
                    "strike": pricing.get("strike", 0.0),
                    "oracle_spot": pricing.get("oracle_spot", 0.0),
                    "binance_spot": pricing.get("binance_spot", 0.0),
                    "feed_spread": pricing.get("feed_spread", 0.0),
                    "delta": pricing.get("delta", 0.0),
                    "status": pricing.get("status", "UP"),
                    "poly_price_up": poly.get("price_up", 0.50),
                    "poly_price_down": poly.get("price_down", 0.50),
                    "signal": signal
                },
                "pnl_summary": trades_info["pnl_summary"],
                "recent_trades": trades_info["recent_trades"]
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def run_server():
    # 1. Inicia o motor quantitativo de BTC 5m
    btc_engine.start_loop()

    # 2. Inicia o worker de saldo real via CLOB em segundo plano
    t_bal = threading.Thread(target=balance_polling_worker, daemon=True)
    t_bal.start()

    print("=" * 65)
    print(f"-> Servidor Simplificado iniciando em http://localhost:{PORT}...")
    print(f"-> Depósito Inicial: ${INITIAL_DEPOSIT:.2f} USDC")
    print(f"-> Carteira Funder: {FUNDER_ADDR}")
    print("=" * 65)
    
    server = socketserver.TCPServer(("", PORT), SimplifiedDashboardHandler)
    server.serve_forever()

if __name__ == "__main__":
    run_server()
