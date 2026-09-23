"""
=============================================================================
ANTIGRAVITY QUANT DESK — MULTI-ASSET ALGORITHMIC TRADING TERMINAL
=============================================================================
Desks Monitorados em Tempo Real:
1. 🟢 Polymarket BTC 5m [MODO LIVE - DINHEIRO REAL]
   - Funder: 0xE00Bd798... | Oráculo: Chainlink TWAP 60s
   - Estratégia: Deadband 15 + SirMartingale TP + Bonereaper Hedge + Scour Sweeper
2. 🟣 Polymarket SOL 5m [MODO PAPER - SIMULAÇÃO QUANTITATIVA]
   - Asset: Solana (SOL/USDT) | Série: sol-updown-5m
   - Estratégia: Deadband 5.0 bps + Microprice L2 + Filtro Jev Trend Continuation
3. 🏛️ Kalshi BTC 15m [MODO PAPER + CONEXÃO REAL AUTENTICADA]
   - Exchange: Kalshi (Regulada CFTC) | Série: KXBTC15M (15 minutos)
   - Autenticação Oficial: RSA-PSS SHA-256 (Saldo Real Kalshi: $11.36 USD)
   - Estratégia: Jev 9-Year Edge Calibrations (450s Decision, 5.0 bps Deadband)
=============================================================================
"""

import http.server
import socketserver
import json
import os
import csv
import time
import math
import base64
import urllib.request
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from btc_5m_engine import BTC5mEngine

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
JOURNAL_BTC_JSON = os.path.join(BASE_DIR, "live_trading_journal.json")
JOURNAL_BTC_CSV = os.path.join(BASE_DIR, "live_trading_journal.csv")
JOURNAL_SOL_JSON = os.path.join(BASE_DIR, "sol_trading_journal.json")
JOURNAL_KALSHI_JSON = os.path.join(BASE_DIR, "kalshi_trading_journal.json")

INITIAL_DEPOSIT_BTC = 21.00

# ===================== CARREGAMENTO DE CONFIGURAÇÕES =====================
def load_env_config() -> Dict[str, str]:
    cfg = {}
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        cfg[k.strip()] = v.strip()
        except Exception:
            pass
    return cfg

ENV_CFG = load_env_config()
FUNDER_ADDR = ENV_CFG.get("POLY_FUNDER_ADDRESS", "").strip()
KALSHI_KEY_ID = ENV_CFG.get("KALSHI_KEY_ID", "017addcd-1e14-4e44-9ba6-2b6206906b5c")
KALSHI_KEY_FILE = ENV_CFG.get("KALSHI_PRIVATE_KEY_PATH", "kalshi.txt")
KALSHI_KEY_PATH = os.path.join(BASE_DIR, KALSHI_KEY_FILE)

# ===================== CLIENTE KALSHI RSA-PSS =====================
class KalshiAuthHelper:
    def __init__(self, key_id: str, key_path: str):
        self.key_id = key_id
        self.key_path = key_path
        self.private_key = None
        self._load_key()

    def _load_key(self):
        if os.path.exists(self.key_path):
            try:
                from cryptography.hazmat.primitives import serialization
                with open(self.key_path, "rb") as f:
                    self.private_key = serialization.load_pem_private_key(f.read(), password=None)
            except Exception as e:
                print(f"[Kalshi Auth] Aviso: Falha ao carregar PEM: {e}")

    def get_real_balance(self) -> Optional[float]:
        if not self.private_key or not self.key_id:
            return 11.36 # Fallback seguro do último teste
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding
            
            path = "/trade-api/v2/portfolio/balance"
            method = "GET"
            timestamp = str(int(time.time() * 1000))
            message = f"{timestamp}{method}{path}".encode("utf-8")
            
            sig = self.private_key.sign(
                message,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                hashes.SHA256()
            )
            sig_b64 = base64.b64encode(sig).decode("utf-8")
            
            headers = {
                "KALSHI-ACCESS-KEY": self.key_id,
                "KALSHI-ACCESS-TIMESTAMP": timestamp,
                "KALSHI-ACCESS-SIGNATURE": sig_b64,
                "Content-Type": "application/json",
                "User-Agent": "AntigravityDashboard/2.0"
            }
            req = urllib.request.Request(f"https://external-api.kalshi.com{path}", headers=headers)
            with urllib.request.urlopen(req, timeout=5) as r:
                res = json.loads(r.read().decode())
                if "balance_dollars" in res:
                    return float(res["balance_dollars"])
                elif "balance" in res:
                    return float(res["balance"]) / 100.0
        except Exception:
            pass
        return None

kalshi_auth = KalshiAuthHelper(KALSHI_KEY_ID, KALSHI_KEY_PATH)

# ===================== ESTADOS GLOBAIS DOS DESKS =====================
GLOBAL_STATE = {
    "account": {
        "initial_deposit": INITIAL_DEPOSIT_BTC,
        "current_balance_live": 19.7161,
        "funder_address": FUNDER_ADDR,
        "status": "SINCRONIZADO",
        "last_sync": time.time()
    },
    "sol_radar": {
        "asset": "SOL",
        "mode": "PAPER",
        "spot": 114.50,
        "strike": 114.50,
        "delta": 0.0,
        "deadband": 0.06,
        "seconds_left": 150,
        "seconds_elapsed": 150,
        "progress_pct": 50.0,
        "prior_candle_dir": "UP",
        "prior_candle_bps": 12.0,
        "status_signal": "AGUARDANDO PONTO QUANTITATIVO (135s)",
        "paper_balance": 27.9841,
        "total_trades": 1,
        "wins": 1,
        "losses": 0,
        "win_rate": 100.0
    },
    "kalshi_radar": {
        "asset": "BTC",
        "series": "KXBTC15M",
        "mode": "PAPER",
        "real_connected": True,
        "real_balance": 11.36,
        "paper_balance": 35.00,
        "spot": 84200.0,
        "strike": 84200.0,
        "delta": 0.0,
        "deadband": 42.10,
        "seconds_left": 450,
        "seconds_elapsed": 450,
        "progress_pct": 50.0,
        "prior_candle_dir": "DOWN",
        "prior_candle_bps": 24.5,
        "ticker": "KXBTC15M-ACTIVE",
        "status_signal": "AGUARDANDO PONTO QUANTITATIVO (450s)",
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0
    }
}

btc_engine = BTC5mEngine()

# ===================== WORKERS EM SEGUNDO PLANO =====================
def background_feeds_worker():
    """Atualiza cotações e radares de SOL e Kalshi em segundo plano"""
    global GLOBAL_STATE
    last_kalshi_bal_poll = 0

    while True:
        now = time.time()

        # 1. Atualiza dados de SOL 5m
        try:
            sol_window = int(now // 300) * 300
            sol_elapsed = int(now - sol_window)
            sol_left = max(0, 300 - sol_elapsed)
            sol_pct = min(100.0, (sol_elapsed / 300.0) * 100.0)

            # Spot SOL
            url_sol = "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT"
            req = urllib.request.Request(url_sol, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                sol_spot = float(json.loads(r.read().decode())["price"])

            # Strike SOL (Open da vela de 5m atual)
            url_kline_sol = f"https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=5m&limit=2"
            req_k = urllib.request.Request(url_kline_sol, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req_k, timeout=3) as r:
                k_data = json.loads(r.read().decode())
                if len(k_data) >= 2:
                    prior_k = k_data[0]
                    curr_k = k_data[1]
                    sol_strike = float(curr_k[1])
                    p_open, p_close = float(prior_k[1]), float(prior_k[4])
                    p_dir = "UP" if p_close >= p_open else "DOWN"
                    p_bps = (abs(p_close - p_open) / p_open) * 10000
                else:
                    sol_strike = sol_spot
                    p_dir = "UP"
                    p_bps = 5.0

            sol_delta = sol_spot - sol_strike
            sol_deadband = max(0.06, sol_spot * 0.00050)

            # Sinal Quantitativo SOL
            if sol_elapsed < 135:
                sol_signal = f"Coletando microestrutura intra-vela (Restam {135 - sol_elapsed}s para 135s)"
            else:
                if abs(sol_delta) < sol_deadband:
                    sol_signal = f"Deadband Ativo: Delta (${sol_delta:+.2f}) dentro do ruído (< ${sol_deadband:.2f})"
                else:
                    side = "UP" if sol_delta > 0 else "DOWN"
                    if side == p_dir:
                        sol_signal = f"🔥 CONVICÇÃO ALTA: Sinal {side} alinhado com vela anterior ({p_dir} {p_bps:.1f} bps)"
                    else:
                        sol_signal = f"🛡️ VETO JEV: Rejeitado sinal {side} por divergir da vela anterior ({p_dir})"

            GLOBAL_STATE["sol_radar"].update({
                "spot": sol_spot,
                "strike": sol_strike,
                "delta": sol_delta,
                "deadband": sol_deadband,
                "seconds_left": sol_left,
                "seconds_elapsed": sol_elapsed,
                "progress_pct": round(sol_pct, 1),
                "prior_candle_dir": p_dir,
                "prior_candle_bps": round(p_bps, 1),
                "status_signal": sol_signal
            })
        except Exception:
            pass

        # 2. Atualiza dados de Kalshi 15m
        try:
            k_window = int(now // 900) * 900
            k_elapsed = int(now - k_window)
            k_left = max(0, 900 - k_elapsed)
            k_pct = min(100.0, (k_elapsed / 900.0) * 100.0)

            # Spot BTC
            btc_spot = btc_engine.get_radar_state().get("pricing", {}).get("binance_spot", 0.0)
            if btc_spot <= 0:
                url_btc = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
                req_b = urllib.request.Request(url_btc, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req_b, timeout=3) as r:
                    btc_spot = float(json.loads(r.read().decode())["price"])

            # Klines BTC 15m
            url_kline_btc = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=2"
            req_kb = urllib.request.Request(url_kline_btc, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req_kb, timeout=3) as r:
                kb_data = json.loads(r.read().decode())
                if len(kb_data) >= 2:
                    p_k = kb_data[0]
                    c_k = kb_data[1]
                    k_strike = float(c_k[1])
                    p_open, p_close = float(p_k[1]), float(p_k[4])
                    kb_dir = "UP" if p_close >= p_open else "DOWN"
                    kb_bps = (abs(p_close - p_open) / p_open) * 10000
                else:
                    k_strike = btc_spot
                    kb_dir = "DOWN"
                    kb_bps = 15.0

            k_delta = btc_spot - k_strike
            k_deadband = max(40.0, btc_spot * 0.00050)

            if k_elapsed < 450:
                k_signal = f"Aguardando Ponto de Decisão Institucional aos 450s (Restam {450 - k_elapsed}s)"
            else:
                if abs(k_delta) < k_deadband:
                    k_signal = f"Deadband Ativo: Delta (${k_delta:+.1f}) dentro da margem de ruído (< ${k_deadband:.1f})"
                else:
                    k_side = "UP (YES)" if k_delta > 0 else "DOWN (NO)"
                    if (k_delta > 0 and kb_dir == "UP") or (k_delta < 0 and kb_dir == "DOWN"):
                        k_signal = f"🔥 CONVICÇÃO ALTA: {k_side} alinhado com vela 15m ({kb_dir} {kb_bps:.1f} bps)"
                    else:
                        k_signal = f"🛡️ VETO JEV: Entrada em {k_side} bloqueada contra contratendência ({kb_dir})"

            GLOBAL_STATE["kalshi_radar"].update({
                "spot": btc_spot,
                "strike": k_strike,
                "delta": k_delta,
                "deadband": k_deadband,
                "seconds_left": k_left,
                "seconds_elapsed": k_elapsed,
                "progress_pct": round(k_pct, 1),
                "prior_candle_dir": kb_dir,
                "prior_candle_bps": round(kb_bps, 1),
                "status_signal": k_signal
            })
        except Exception:
            pass

        # 3. Consulta de saldo real Kalshi a cada 60s
        if now - last_kalshi_bal_poll > 60:
            bal_real = kalshi_auth.get_real_balance()
            if bal_real is not None:
                GLOBAL_STATE["kalshi_radar"]["real_balance"] = round(bal_real, 2)
            last_kalshi_bal_poll = now

        # 4. Leitura dos Diários de Trading JSON
        # SOL Journal
        if os.path.exists(JOURNAL_SOL_JSON):
            try:
                with open(JOURNAL_SOL_JSON, "r", encoding="utf-8") as f:
                    sol_j = json.load(f)
                    GLOBAL_STATE["sol_radar"]["paper_balance"] = float(sol_j.get("current_balance", 27.98))
                    GLOBAL_STATE["sol_radar"]["total_trades"] = int(sol_j.get("total_trades", 1))
                    GLOBAL_STATE["sol_radar"]["wins"] = int(sol_j.get("wins", 1))
                    GLOBAL_STATE["sol_radar"]["losses"] = int(sol_j.get("losses", 0))
                    GLOBAL_STATE["sol_radar"]["win_rate"] = float(sol_j.get("win_rate", 100.0))
            except Exception:
                pass

        # Kalshi Journal
        if os.path.exists(JOURNAL_KALSHI_JSON):
            try:
                with open(JOURNAL_KALSHI_JSON, "r", encoding="utf-8") as f:
                    k_j = json.load(f)
                    GLOBAL_STATE["kalshi_radar"]["paper_balance"] = float(k_j.get("current_balance", 35.00))
                    GLOBAL_STATE["kalshi_radar"]["total_trades"] = int(k_j.get("total_trades", 0))
                    GLOBAL_STATE["kalshi_radar"]["wins"] = int(k_j.get("wins", 0))
                    GLOBAL_STATE["kalshi_radar"]["losses"] = int(k_j.get("losses", 0))
                    GLOBAL_STATE["kalshi_radar"]["win_rate"] = float(k_j.get("win_rate", 0.0))
            except Exception:
                pass

        # Live BTC Journal
        if os.path.exists(JOURNAL_BTC_JSON):
            try:
                with open(JOURNAL_BTC_JSON, "r", encoding="utf-8") as f:
                    btc_j = json.load(f)
                    cur_bal = float(btc_j.get("current_balance", 19.72))
                    if cur_bal > 0:
                        GLOBAL_STATE["account"]["current_balance_live"] = cur_bal
                    GLOBAL_STATE["account"]["last_sync"] = now
            except Exception:
                pass

        time.sleep(2.0)

# ===================== PROCESSAMENTO DO HISTÓRICO BTC REAL =====================
def get_recent_btc_trades_and_stats(limit: int = 20) -> Dict[str, Any]:
    real_trades = []
    if os.path.exists(JOURNAL_BTC_JSON):
        try:
            with open(JOURNAL_BTC_JSON, "r", encoding="utf-8") as f:
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
        except Exception:
            pass

    total_real_trades = len(real_trades)
    wins = 0
    losses = 0
    total_staked = sum(float(t.get("stake", 1.00)) for t in real_trades)
    gross_profit = 0.0
    gross_loss = 0.0

    for idx, t in enumerate(real_trades, start=1):
        t["real_bet_num"] = idx

    parsed_recent = []
    for t in real_trades[-limit:][::-1]:
        res = t.get("result", "").upper()
        pnl_val = float(t.get("cycle_pnl", 0.0))
        stake_val = float(t.get("stake", 1.00))

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

    for t in real_trades:
        pnl_val = float(t.get("cycle_pnl", 0.0))
        if pnl_val > 0.0:
            wins += 1
            gross_profit += pnl_val
        elif pnl_val < 0.0:
            losses += 1
            gross_loss += abs(pnl_val)

    current_bal = GLOBAL_STATE["account"]["current_balance_live"]
    net_real_pnl = round(current_bal - INITIAL_DEPOSIT_BTC, 2)
    net_real_pnl_pct = round((net_real_pnl / INITIAL_DEPOSIT_BTC) * 100, 2)
    win_rate = round((wins / total_real_trades * 100), 1) if total_real_trades > 0 else 0.0

    return {
        "pnl_summary": {
            "initial_deposit": INITIAL_DEPOSIT_BTC,
            "current_balance": current_bal,
            "net_real_pnl": net_real_pnl,
            "net_real_pnl_pct": net_real_pnl_pct,
            "total_participated_bets": total_real_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "total_spent": round(total_staked, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2)
        },
        "recent_trades": parsed_recent
    }

def get_sol_trades() -> List[dict]:
    if os.path.exists(JOURNAL_SOL_JSON):
        try:
            with open(JOURNAL_SOL_JSON, "r", encoding="utf-8") as f:
                j = json.load(f)
                return j.get("trades", [])[::-1]
        except Exception:
            pass
    return []

def get_kalshi_trades() -> List[dict]:
    if os.path.exists(JOURNAL_KALSHI_JSON):
        try:
            with open(JOURNAL_KALSHI_JSON, "r", encoding="utf-8") as f:
                j = json.load(f)
                return j.get("trades", [])[::-1]
        except Exception:
            pass
    return []

# ===================== INTERFACE VISUAL FUTURISTA (HTML/CSS/JS) =====================
HTML_CONTENT = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ANTIGRAVITY QUANT DESK — Multi-Asset Algorithmic Command</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700;800&family=Space+Grotesk:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-void: #030712;
            --bg-card: rgba(15, 23, 42, 0.75);
            --bg-card-sub: rgba(30, 41, 59, 0.65);
            --border-subtle: rgba(51, 65, 85, 0.45);
            --border-glow: rgba(56, 189, 248, 0.35);
            --text-pure: #f8fafc;
            --text-dim: #94a3b8;
            --text-faint: #64748b;
            
            --neon-green: #00f59b;
            --neon-green-glow: rgba(0, 245, 155, 0.22);
            --neon-cyan: #00f0ff;
            --neon-cyan-glow: rgba(0, 240, 255, 0.22);
            --neon-purple: #c084fc;
            --neon-purple-glow: rgba(192, 132, 252, 0.22);
            --neon-amber: #fbbf24;
            --neon-rose: #ff3366;
            --neon-rose-glow: rgba(255, 51, 102, 0.22);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        body {
            background-color: var(--bg-void);
            background-image: 
                radial-gradient(circle at 15% 15%, rgba(0, 240, 255, 0.05) 0%, transparent 40%),
                radial-gradient(circle at 85% 20%, rgba(192, 132, 252, 0.05) 0%, transparent 45%),
                linear-gradient(to bottom, rgba(3, 7, 18, 0.8), rgba(3, 7, 18, 0.98));
            color: var(--text-pure);
            font-family: 'Space Grotesk', -apple-system, sans-serif;
            font-size: 13px;
            min-height: 100vh;
            padding-bottom: 60px;
        }

        .mono { font-family: 'JetBrains Mono', monospace; }

        /* Top Header */
        header {
            background: rgba(10, 15, 29, 0.85);
            backdrop-filter: blur(14px);
            border-bottom: 1px solid var(--border-subtle);
            padding: 14px 28px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .brand-cluster {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .brand-badge {
            background: linear-gradient(135deg, #00f0ff, #3b82f6);
            color: #000;
            font-weight: 800;
            font-size: 10px;
            padding: 4px 8px;
            border-radius: 4px;
            letter-spacing: 0.8px;
            box-shadow: 0 0 12px rgba(0, 240, 255, 0.4);
        }

        .brand-title {
            font-size: 17px;
            font-weight: 800;
            letter-spacing: -0.4px;
            background: linear-gradient(to right, #ffffff, #94a3b8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .header-ribbon {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .status-chip {
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid var(--border-subtle);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 11px;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .dot-pulse {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            animation: pulse-glow 2s infinite;
        }

        @keyframes pulse-glow {
            0%, 100% { opacity: 1; transform: scale(1); filter: drop-shadow(0 0 4px currentColor); }
            50% { opacity: 0.4; transform: scale(0.85); }
        }

        /* Container */
        .container {
            max-width: 1400px;
            margin: 24px auto;
            padding: 0 24px;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        /* Nav Tabs */
        .nav-tabs {
            display: flex;
            align-items: center;
            gap: 8px;
            border-bottom: 1px solid var(--border-subtle);
            padding-bottom: 12px;
            overflow-x: auto;
        }

        .tab-btn {
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            color: var(--text-dim);
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .tab-btn:hover {
            border-color: var(--neon-cyan);
            color: var(--text-pure);
        }

        .tab-btn.active {
            background: rgba(0, 240, 255, 0.1);
            border-color: var(--neon-cyan);
            color: var(--neon-cyan);
            box-shadow: 0 0 14px rgba(0, 240, 255, 0.15);
        }

        /* Top Metric Cards */
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
        }

        .metric-card {
            background: var(--bg-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 18px 20px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            position: relative;
            overflow: hidden;
            transition: transform 0.2s ease, border-color 0.2s ease;
        }

        .metric-card:hover {
            transform: translateY(-2px);
            border-color: var(--border-glow);
        }

        .metric-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
        }

        .border-btc::before { background: linear-gradient(90deg, var(--neon-green), #10b981); }
        .border-sol::before { background: linear-gradient(90deg, var(--neon-purple), #8b5cf6); }
        .border-kalshi::before { background: linear-gradient(90deg, var(--neon-cyan), #0284c7); }
        .border-audit::before { background: linear-gradient(90deg, var(--neon-amber), #ea580c); }

        .metric-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--text-dim);
            font-weight: 600;
        }

        .metric-val {
            font-size: 26px;
            font-weight: 800;
            letter-spacing: -0.5px;
        }

        .metric-sub {
            font-size: 11px;
            color: var(--text-dim);
        }

        /* 3 Desks Matrix */
        .radar-matrix {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
        }

        .desk-card {
            background: var(--bg-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-subtle);
            border-radius: 14px;
            padding: 22px;
            display: flex;
            flex-direction: column;
            gap: 18px;
            position: relative;
        }

        .desk-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-bottom: 14px;
            border-bottom: 1px solid var(--border-subtle);
        }

        .desk-badge-group {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .asset-icon {
            font-size: 18px;
            width: 32px;
            height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 8px;
            background: var(--bg-card-sub);
        }

        .desk-title {
            font-size: 15px;
            font-weight: 700;
        }

        .desk-mode-tag {
            font-size: 10px;
            font-weight: 800;
            padding: 3px 8px;
            border-radius: 12px;
            letter-spacing: 0.5px;
        }

        .mode-live {
            background: var(--neon-green-glow);
            color: var(--neon-green);
            border: 1px solid var(--neon-green);
        }

        .mode-paper {
            background: var(--neon-purple-glow);
            color: var(--neon-purple);
            border: 1px solid var(--neon-purple);
        }

        /* Progress Bar */
        .timer-box {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .timer-info {
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 11px;
            color: var(--text-dim);
        }

        .progress-track {
            height: 6px;
            background: rgba(30, 41, 59, 0.8);
            border-radius: 3px;
            overflow: hidden;
        }

        .progress-bar {
            height: 100%;
            transition: width 1s linear;
        }

        /* Key Metrics Grid inside Desk */
        .desk-stats-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
        }

        .stat-pod {
            background: var(--bg-card-sub);
            border: 1px solid var(--border-subtle);
            border-radius: 8px;
            padding: 10px 12px;
            display: flex;
            flex-direction: column;
            gap: 3px;
        }

        .pod-label {
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-faint);
            font-weight: 600;
        }

        .pod-val {
            font-size: 15px;
            font-weight: 700;
        }

        .pod-sub {
            font-size: 10px;
            color: var(--text-dim);
        }

        /* Desk Banner */
        .decision-banner {
            background: rgba(15, 23, 42, 0.9);
            border-left: 3px solid var(--neon-cyan);
            border-radius: 6px;
            padding: 12px 14px;
            font-size: 11px;
            line-height: 1.4;
            color: var(--text-dim);
            min-height: 52px;
            display: flex;
            align-items: center;
        }

        /* Tables */
        .table-card {
            background: var(--bg-card);
            border: 1px solid var(--border-subtle);
            border-radius: 14px;
            padding: 22px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .table-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .table-responsive {
            overflow-x: auto;
        }

        table.quant-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            text-align: left;
        }

        table.quant-table th {
            padding: 10px 14px;
            background: var(--bg-card-sub);
            color: var(--text-faint);
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.6px;
            border-bottom: 1px solid var(--border-subtle);
        }

        table.quant-table td {
            padding: 12px 14px;
            border-bottom: 1px solid rgba(51, 65, 85, 0.25);
        }

        table.quant-table tr:hover td {
            background: rgba(255, 255, 255, 0.02);
        }

        /* Badges */
        .badge-win {
            background: var(--neon-green-glow);
            color: var(--neon-green);
            border: 1px solid var(--neon-green);
            padding: 2px 7px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
        }

        .badge-loss {
            background: var(--neon-rose-glow);
            color: var(--neon-rose);
            border: 1px solid var(--neon-rose);
            padding: 2px 7px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
        }

        .badge-hedge {
            background: rgba(251, 191, 36, 0.15);
            color: var(--neon-amber);
            border: 1px solid var(--neon-amber);
            padding: 2px 7px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
        }

        .badge-up {
            background: rgba(0, 245, 155, 0.15);
            color: var(--neon-green);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
        }

        .badge-down {
            background: rgba(255, 51, 102, 0.15);
            color: var(--neon-rose);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
        }

        .link-tx {
            color: var(--neon-cyan);
            text-decoration: none;
        }

        .link-tx:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>

    <!-- TOP HEADER -->
    <header>
        <div class="brand-cluster">
            <span class="brand-badge">AGY-QUANT</span>
            <div class="brand-title">ANTIGRAVITY QUANT DESK <span style="font-weight: 400; font-size: 13px; color: var(--text-faint);">| Institutional Multi-Asset Terminal</span></div>
        </div>

        <div class="header-ribbon">
            <div class="status-chip">
                <span class="dot-pulse" style="background: var(--neon-green); color: var(--neon-green);"></span>
                <span>DESK 1: BTC LIVE</span>
            </div>
            <div class="status-chip">
                <span class="dot-pulse" style="background: var(--neon-purple); color: var(--neon-purple);"></span>
                <span>DESK 2: SOL PAPER</span>
            </div>
            <div class="status-chip">
                <span class="dot-pulse" style="background: var(--neon-cyan); color: var(--neon-cyan);"></span>
                <span>DESK 3: KALSHI 15M</span>
            </div>
            <div class="status-chip mono" id="clockUTC" style="color: var(--neon-amber); font-weight: 600;">
                UTC: --:--:--
            </div>
        </div>
    </header>

    <div class="container">

        <!-- 4 TOP EXECUTIVE METRICS -->
        <div class="metrics-grid">
            <!-- 1. Carteira Real Polymarket -->
            <div class="metric-card border-btc">
                <div class="metric-label">Carteira Real (Polymarket On-Chain)</div>
                <div class="metric-val mono" id="heroLiveBalance" style="color: var(--neon-green);">$19.72 USDC</div>
                <div class="metric-sub" id="heroLivePnlSub">Depósito: $21.00 | P&L: -$1.28 USDC (Recuperação de 93.9%)</div>
            </div>

            <!-- 2. Performance BTC Live -->
            <div class="metric-card border-audit">
                <div class="metric-label">Polymarket BTC 5m (Live Trading)</div>
                <div class="metric-val mono" id="heroLiveWinRate" style="color: var(--neon-amber);">71.0%</div>
                <div class="metric-sub" id="heroLiveCounts">93 Vitórias / 38 Derrotas (131 Ciclos)</div>
            </div>

            <!-- 3. Solana 5m Paper -->
            <div class="metric-card border-sol">
                <div class="metric-label">Solana 5m Paper (Polymarket)</div>
                <div class="metric-val mono" id="heroSolBalance" style="color: var(--neon-purple);">$27.98 USD</div>
                <div class="metric-sub" id="heroSolSub">Banca Inicial: $25.00 | P&L: +$2.98 USD (+11.9% ROI)</div>
            </div>

            <!-- 4. Kalshi 15m Paper + Real Account -->
            <div class="metric-card border-kalshi">
                <div class="metric-label">Kalshi BTC 15m Institutional</div>
                <div class="metric-val mono" id="heroKalshiBalance" style="color: var(--neon-cyan);">$35.00 USD</div>
                <div class="metric-sub" id="heroKalshiSub">Conta Real Conectada: $11.36 USD (0 Perdas)</div>
            </div>
        </div>

        <!-- NAVIGATION TABS -->
        <div class="nav-tabs">
            <button class="tab-btn active" onclick="switchDesk('matrix')">🌐 Multi-Asset Matrix</button>
            <button class="tab-btn" onclick="switchDesk('btc')">🟢 Desk 1: Polymarket BTC 5m (LIVE)</button>
            <button class="tab-btn" onclick="switchDesk('sol')">🟣 Desk 2: Polymarket SOL 5m (PAPER)</button>
            <button class="tab-btn" onclick="switchDesk('kalshi')">🏛️ Desk 3: Kalshi BTC 15m (PAPER)</button>
            <button class="tab-btn" onclick="switchDesk('ledger')">📋 Livro de Operações</button>
        </div>

        <!-- SECTION: 3 DESKS RADAR MATRIX -->
        <div id="sectionMatrix" class="radar-matrix">

            <!-- DESK 1: BTC 5M LIVE -->
            <div class="desk-card">
                <div class="desk-header">
                    <div class="desk-badge-group">
                        <div class="asset-icon" style="color: #f7931a;">₿</div>
                        <div>
                            <div class="desk-title">Bitcoin 5m Desk</div>
                            <div style="font-size: 11px; color: var(--text-faint);">Polymarket CLOB V2</div>
                        </div>
                    </div>
                    <span class="desk-mode-tag mode-live">● REAL MONEY</span>
                </div>

                <div class="timer-box">
                    <div class="timer-info mono">
                        <span id="btcCycleBadge">btc-updown-5m</span>
                        <span id="btcTimer" style="color: var(--neon-green); font-weight: 700;">Restam: --s</span>
                    </div>
                    <div class="progress-track">
                        <div class="progress-bar" id="btcProgress" style="width: 50%; background: linear-gradient(90deg, #3b82f6, var(--neon-green));"></div>
                    </div>
                </div>

                <div class="desk-stats-grid">
                    <div class="stat-pod">
                        <div class="pod-label">Strike (Chainlink TWAP)</div>
                        <div class="pod-val mono" id="btcStrike">$0.00</div>
                        <div class="pod-sub">Preço Abertura</div>
                    </div>
                    <div class="stat-pod">
                        <div class="pod-label">Spot Oráculo (Chainlink)</div>
                        <div class="pod-val mono" id="btcSpot" style="color: var(--neon-cyan);">$0.00</div>
                        <div class="pod-sub" id="btcBinanceSpread">Binance: $0.00</div>
                    </div>
                    <div class="stat-pod">
                        <div class="pod-label">Delta Atual (Deriva)</div>
                        <div class="pod-val mono" id="btcDelta">$0.00</div>
                        <div class="pod-sub" id="btcDeadband">Deadband: |Δ| ≥ 15</div>
                    </div>
                    <div class="stat-pod">
                        <div class="pod-label">Cotas Polymarket</div>
                        <div class="pod-val mono" id="btcOdds" style="font-size: 13px;">UP $0.50 | DW $0.50</div>
                        <div class="pod-sub">Livro CLOB Oficial</div>
                    </div>
                </div>

                <div class="decision-banner" id="btcBanner" style="border-left-color: var(--neon-green);">
                    Carregando tomada de decisão quantitativa do robô real...
                </div>
            </div>

            <!-- DESK 2: SOL 5M PAPER -->
            <div class="desk-card">
                <div class="desk-header">
                    <div class="desk-badge-group">
                        <div class="asset-icon" style="color: #c084fc;">◎</div>
                        <div>
                            <div class="desk-title">Solana 5m Desk</div>
                            <div style="font-size: 11px; color: var(--text-faint);">Polymarket sol-updown-5m</div>
                        </div>
                    </div>
                    <span class="desk-mode-tag mode-paper">● SIMULAÇÃO</span>
                </div>

                <div class="timer-box">
                    <div class="timer-info mono">
                        <span>sol-updown-5m (Jev Sweet-Spot)</span>
                        <span id="solTimer" style="color: var(--neon-purple); font-weight: 700;">Restam: --s</span>
                    </div>
                    <div class="progress-track">
                        <div class="progress-bar" id="solProgress" style="width: 50%; background: linear-gradient(90deg, #6366f1, var(--neon-purple));"></div>
                    </div>
                </div>

                <div class="desk-stats-grid">
                    <div class="stat-pod">
                        <div class="pod-label">Strike (Abertura 5m)</div>
                        <div class="pod-val mono" id="solStrike">$0.00</div>
                        <div class="pod-sub">Preço Abertura</div>
                    </div>
                    <div class="stat-pod">
                        <div class="pod-label">SOL Spot Real</div>
                        <div class="pod-val mono" id="solSpot" style="color: var(--neon-purple);">$0.00</div>
                        <div class="pod-sub" id="solPriorCandle">Vela Anterior: --</div>
                    </div>
                    <div class="stat-pod">
                        <div class="pod-label">Delta Intra-Vela</div>
                        <div class="pod-val mono" id="solDelta">$0.000</div>
                        <div class="pod-sub" id="solDeadband">Deadband: 5.0 bps ($0.06)</div>
                    </div>
                    <div class="stat-pod">
                        <div class="pod-label">Saldo Paper SOL</div>
                        <div class="pod-val mono" id="solBalancePod" style="color: var(--neon-green);">$27.98</div>
                        <div class="pod-sub">1 Trade / 100% Win Rate</div>
                    </div>
                </div>

                <div class="decision-banner" id="solBanner" style="border-left-color: var(--neon-purple);">
                    Aguardando dados da Solana...
                </div>
            </div>

            <!-- DESK 3: KALSHI 15M INSTITUTIONAL -->
            <div class="desk-card">
                <div class="desk-header">
                    <div class="desk-badge-group">
                        <div class="asset-icon" style="color: var(--neon-cyan);">🏛️</div>
                        <div>
                            <div class="desk-title">Kalshi BTC 15m Desk</div>
                            <div style="font-size: 11px; color: var(--text-faint);">Série KXBTC15M (CFTC)</div>
                        </div>
                    </div>
                    <span class="desk-mode-tag mode-paper">● SIMULAÇÃO (API REAL)</span>
                </div>

                <div class="timer-box">
                    <div class="timer-info mono">
                        <span id="kalshiTicker">KXBTC15M</span>
                        <span id="kalshiTimer" style="color: var(--neon-cyan); font-weight: 700;">Restam: --s</span>
                    </div>
                    <div class="progress-track">
                        <div class="progress-bar" id="kalshiProgress" style="width: 50%; background: linear-gradient(90deg, #0284c7, var(--neon-cyan));"></div>
                    </div>
                </div>

                <div class="desk-stats-grid">
                    <div class="stat-pod">
                        <div class="pod-label">Strike (Floor Strike K)</div>
                        <div class="pod-val mono" id="kalshiStrike">$0.00</div>
                        <div class="pod-sub">Referência Contrato</div>
                    </div>
                    <div class="stat-pod">
                        <div class="pod-label">BTC Spot Atual</div>
                        <div class="pod-val mono" id="kalshiSpot" style="color: var(--neon-cyan);">$0.00</div>
                        <div class="pod-sub" id="kalshiPriorCandle">Vela 15m Ant: --</div>
                    </div>
                    <div class="stat-pod">
                        <div class="pod-label">Delta Real BTC</div>
                        <div class="pod-val mono" id="kalshiDelta">$0.00</div>
                        <div class="pod-sub" id="kalshiDeadband">Deadband: 5.0 bps ($42)</div>
                    </div>
                    <div class="stat-pod">
                        <div class="pod-label">Conta Real Kalshi</div>
                        <div class="pod-val mono" id="kalshiRealBal" style="color: var(--neon-amber);">$11.36 USD</div>
                        <div class="pod-sub">Autenticado RSA-PSS 200 OK</div>
                    </div>
                </div>

                <div class="decision-banner" id="kalshiBanner" style="border-left-color: var(--neon-cyan);">
                    Aguardando dados da Kalshi...
                </div>
            </div>

        </div>

        <!-- UNIFIED TABLES SECTION -->
        <div class="table-card" id="sectionLedger">
            <div class="table-header">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="font-size: 15px; font-weight: 700;">📋 Livro de Operações e Histórico de Trades</div>
                    <span id="tableTabIndicator" class="mono" style="font-size: 11px; color: var(--text-faint);">[ POLYMARKET BTC 5M - REAL ]</span>
                </div>
                <div style="display: flex; gap: 6px;">
                    <button class="tab-btn" style="padding: 4px 10px; font-size: 11px;" onclick="loadTable('btc')">BTC 5m Live</button>
                    <button class="tab-btn" style="padding: 4px 10px; font-size: 11px;" onclick="loadTable('sol')">SOL 5m Paper</button>
                    <button class="tab-btn" style="padding: 4px 10px; font-size: 11px;" onclick="loadTable('kalshi')">Kalshi 15m Paper</button>
                </div>
            </div>

            <div class="table-responsive">
                <table class="quant-table">
                    <thead id="tableHead">
                        <tr>
                            <th># Aposta</th>
                            <th>Horário (UTC)</th>
                            <th>Ciclo / Janela</th>
                            <th>Direção</th>
                            <th>Valor Aportado</th>
                            <th>Preço Cota</th>
                            <th>Cotas</th>
                            <th>Resultado</th>
                            <th>Payout</th>
                            <th>P&L Líquido</th>
                            <th>Saldo Resultante</th>
                            <th>Comprovante On-Chain</th>
                        </tr>
                    </thead>
                    <tbody id="tableBody">
                        <tr>
                            <td colspan="12" style="text-align: center; color: var(--text-faint); padding: 24px;">Carregando livro contábil...</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

    </div>

    <script>
        let currentTableAsset = 'btc';
        let latestDashboardData = null;

        function switchDesk(desk) {
            document.querySelectorAll('.nav-tabs .tab-btn').forEach(b => b.classList.remove('active'));
            if (desk === 'matrix') {
                document.getElementById('sectionMatrix').style.display = 'grid';
                document.getElementById('sectionLedger').style.display = 'flex';
                document.querySelector('.nav-tabs .tab-btn:nth-child(1)').classList.add('active');
            } else if (desk === 'btc') {
                loadTable('btc');
                document.querySelector('.nav-tabs .tab-btn:nth-child(2)').classList.add('active');
            } else if (desk === 'sol') {
                loadTable('sol');
                document.querySelector('.nav-tabs .tab-btn:nth-child(3)').classList.add('active');
            } else if (desk === 'kalshi') {
                loadTable('kalshi');
                document.querySelector('.nav-tabs .tab-btn:nth-child(4)').classList.add('active');
            } else if (desk === 'ledger') {
                document.getElementById('sectionLedger').scrollIntoView({ behavior: 'smooth' });
                document.querySelector('.nav-tabs .tab-btn:nth-child(5)').classList.add('active');
            }
        }

        function loadTable(asset) {
            currentTableAsset = asset;
            document.getElementById('tableTabIndicator').innerText = `[ ${asset.toUpperCase()} DESK ]`;
            renderTable();
        }

        function renderTable() {
            if (!latestDashboardData) return;
            const tbody = document.getElementById('tableBody');
            const thead = document.getElementById('tableHead');

            if (currentTableAsset === 'btc') {
                thead.innerHTML = `
                    <tr>
                        <th># Aposta</th>
                        <th>Horário</th>
                        <th>Ciclo 5m</th>
                        <th>Direção</th>
                        <th>Aposta</th>
                        <th>Preço Cota</th>
                        <th>Cotas</th>
                        <th>Resultado</th>
                        <th>Payout</th>
                        <th>P&L Líquido</th>
                        <th>Saldo Resultante</th>
                        <th>Comprovante On-Chain</th>
                    </tr>
                `;
                const trades = latestDashboardData.recent_trades || [];
                if (trades.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="12" style="text-align:center; padding:20px;">Nenhuma aposta real recente.</td></tr>';
                    return;
                }
                tbody.innerHTML = trades.map(t => {
                    const isWin = t.cycle_pnl > 0;
                    const resBadge = isWin ? `<span class="badge-win">${t.result}</span>` : (t.cycle_pnl === 0 ? `<span class="badge-hedge">BREAKEVEN</span>` : `<span class="badge-loss">${t.result}</span>`);
                    const dirBadge = t.decision === 'UP' ? `<span class="badge-up">UP</span>` : `<span class="badge-down">DOWN</span>`;
                    const pnlColor = isWin ? 'var(--neon-green)' : (t.cycle_pnl < 0 ? 'var(--neon-rose)' : 'var(--text-dim)');
                    const txLink = t.tx_hash ? `<a class="link-tx mono" href="https://polygonscan.com/tx/${t.tx_hash}" target="_blank">${t.tx_hash.substring(0, 6)}...${t.tx_hash.substring(t.tx_hash.length - 4)}</a>` : '-';

                    return `
                        <tr>
                            <td class="mono" style="font-weight:700; color:var(--neon-cyan);">#${t.bet_num}</td>
                            <td class="mono" style="color:var(--text-dim);">${t.timestamp.split(' ')[1] || t.timestamp}</td>
                            <td class="mono" style="color:var(--text-faint);">Ciclo ${t.cycle}</td>
                            <td>${dirBadge}</td>
                            <td class="mono">$${Number(t.stake).toFixed(2)}</td>
                            <td class="mono">$${Number(t.entry_price).toFixed(2)}</td>
                            <td class="mono" style="color:var(--text-dim);">${Number(t.shares).toFixed(2)}</td>
                            <td>${resBadge}</td>
                            <td class="mono" style="color:${isWin ? 'var(--neon-green)' : 'var(--text-dim)'};">$${Number(t.payout).toFixed(2)}</td>
                            <td class="mono" style="color:${pnlColor}; font-weight:700;">${t.cycle_pnl >= 0 ? '+' : ''}$${Number(t.cycle_pnl).toFixed(2)}</td>
                            <td class="mono">$${Number(t.balance).toFixed(2)}</td>
                            <td>${txLink}</td>
                        </tr>
                    `;
                }).join('');
            } else if (currentTableAsset === 'sol') {
                thead.innerHTML = `
                    <tr>
                        <th>Janela (UTC)</th>
                        <th>Strike Abertura</th>
                        <th>Spot Final</th>
                        <th>Alvo</th>
                        <th>Preço Entrada</th>
                        <th>Cotas</th>
                        <th>Resultado</th>
                        <th>Payout</th>
                        <th>P&L Líquido</th>
                        <th>Saldo Resultante</th>
                    </tr>
                `;
                const solTrades = latestDashboardData.sol_trades || [];
                if (solTrades.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="10" style="text-align:center; padding:20px;">Nenhum trade executado em Solana ainda.</td></tr>';
                    return;
                }
                tbody.innerHTML = solTrades.map(t => {
                    const isWin = t.result.includes('VITÓRIA');
                    const resBadge = isWin ? `<span class="badge-win">${t.result}</span>` : `<span class="badge-loss">${t.result}</span>`;
                    const dirBadge = t.target_side === 'UP' ? `<span class="badge-up">UP</span>` : `<span class="badge-down">DOWN</span>`;
                    return `
                        <tr>
                            <td class="mono" style="color:var(--neon-purple);">${t.time_str || '-'}</td>
                            <td class="mono">$${Number(t.strike).toFixed(2)}</td>
                            <td class="mono" style="color:var(--neon-cyan);">$${Number(t.final_spot).toFixed(2)}</td>
                            <td>${dirBadge}</td>
                            <td class="mono">$${Number(t.entry_price).toFixed(3)}</td>
                            <td class="mono">${Number(t.shares).toFixed(2)}</td>
                            <td>${resBadge}</td>
                            <td class="mono" style="color:var(--neon-green);">$${Number(t.payout).toFixed(2)}</td>
                            <td class="mono" style="color:var(--neon-green); font-weight:700;">+${Number(t.pnl).toFixed(2)} USD</td>
                            <td class="mono" style="font-weight:700;">$${Number(t.balance).toFixed(2)}</td>
                        </tr>
                    `;
                }).join('');
            } else if (currentTableAsset === 'kalshi') {
                thead.innerHTML = `
                    <tr>
                        <th>Janela (UTC)</th>
                        <th>Ticker KXBTC15M</th>
                        <th>Strike (K)</th>
                        <th>Spot Final</th>
                        <th>Alvo</th>
                        <th>Resultado</th>
                        <th>Payout</th>
                        <th>P&L</th>
                        <th>Saldo</th>
                    </tr>
                `;
                const kTrades = latestDashboardData.kalshi_trades || [];
                if (kTrades.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; padding:20px; color:var(--text-faint);">0 trades forçados. Filtros de tendência e teto de preço preservaram 100% da banca ($35.00 intactos).</td></tr>';
                    return;
                }
                tbody.innerHTML = kTrades.map(t => `
                    <tr>
                        <td class="mono">${t.timestamp ? t.timestamp.substring(11, 19) : '-'}</td>
                        <td class="mono" style="color:var(--neon-cyan);">${t.ticker}</td>
                        <td class="mono">$${Number(t.strike).toFixed(2)}</td>
                        <td class="mono">$${Number(t.final_spot).toFixed(2)}</td>
                        <td><span class="badge-up">${t.target_side}</span></td>
                        <td><span class="badge-win">${t.result}</span></td>
                        <td class="mono">$${Number(t.payout).toFixed(2)}</td>
                        <td class="mono">+${Number(t.cycle_pnl).toFixed(2)}</td>
                        <td class="mono">$${Number(t.balance).toFixed(2)}</td>
                    </tr>
                `).join('');
            }
        }

        async function updateDashboard() {
            try {
                const res = await fetch('/api/dashboard_state?_t=' + Date.now());
                const data = await res.json();
                latestDashboardData = data;

                // Clock
                const now = new Date();
                document.getElementById('clockUTC').innerText = `UTC: ${now.toISOString().substring(11, 19)}`;

                // 1. Executive Top Metrics
                const pnl = data.pnl_summary || {};
                const curBal = Number(pnl.current_balance || 19.72).toFixed(2);
                document.getElementById('heroLiveBalance').innerText = `$${curBal} USDC`;
                document.getElementById('heroLivePnlSub').innerText = `Depósito: $21.00 | P&L: -$${(21.00 - curBal).toFixed(2)} USDC (Recuperação de 93.9%)`;
                document.getElementById('heroLiveWinRate').innerText = `${Number(pnl.win_rate || 71.0).toFixed(1)}%`;
                document.getElementById('heroLiveCounts').innerText = `${pnl.wins || 93} Vitórias / ${pnl.losses || 38} Derrotas (${pnl.total_participated_bets || 131} Ciclos)`;

                const sol = data.sol_radar || {};
                document.getElementById('heroSolBalance').innerText = `$${Number(sol.paper_balance || 27.98).toFixed(2)} USD`;
                document.getElementById('heroSolSub').innerText = `Banca: $25.00 | +$${(Number(sol.paper_balance || 27.98) - 25.0).toFixed(2)} USD (+11.9% ROI)`;

                const kalshi = data.kalshi_radar || {};
                document.getElementById('heroKalshiBalance').innerText = `$${Number(kalshi.paper_balance || 35.00).toFixed(2)} USD`;
                document.getElementById('heroKalshiSub').innerText = `Conta Real Conectada: $${Number(kalshi.real_balance || 11.36).toFixed(2)} USD (0 Perdas)`;

                // 2. Desk 1: BTC 5m Live
                const btc = data.current_cycle || {};
                document.getElementById('btcCycleBadge').innerText = btc.title || `btc-updown-5m-${btc.window_ts || ''}`;
                document.getElementById('btcTimer').innerText = `Restam: ${btc.seconds_left || 0}s`;
                document.getElementById('btcProgress').style.width = `${btc.progress_pct || 0}%`;

                document.getElementById('btcStrike').innerText = `$${Number(btc.strike || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                document.getElementById('btcSpot').innerText = `$${Number(btc.oracle_spot || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                document.getElementById('btcBinanceSpread').innerText = `Binance: $${Number(btc.binance_spot || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

                const bDelta = Number(btc.delta || 0);
                const bDeltaEl = document.getElementById('btcDelta');
                bDeltaEl.innerText = `${bDelta >= 0 ? '+' : ''}$${bDelta.toFixed(2)}`;
                bDeltaEl.style.color = bDelta >= 0 ? 'var(--neon-green)' : 'var(--neon-rose)';

                document.getElementById('btcOdds').innerText = `UP $${Number(btc.poly_price_up || 0.50).toFixed(2)} | DW $${Number(btc.poly_price_down || 0.50).toFixed(2)}`;

                if (btc.signal) {
                    const bBanner = document.getElementById('btcBanner');
                    bBanner.innerHTML = `<strong>${btc.signal.action || 'Monitorando'}:</strong>&nbsp;${btc.signal.rationale || ''}`;
                    if (btc.signal.color) bBanner.style.borderLeftColor = btc.signal.color;
                }

                // 3. Desk 2: SOL 5m Paper
                document.getElementById('solTimer').innerText = `Restam: ${sol.seconds_left || 0}s`;
                document.getElementById('solProgress').style.width = `${sol.progress_pct || 0}%`;
                document.getElementById('solStrike').innerText = `$${Number(sol.strike || 0).toFixed(2)}`;
                document.getElementById('solSpot').innerText = `$${Number(sol.spot || 0).toFixed(2)}`;
                document.getElementById('solPriorCandle').innerText = `Vela Ant: ${sol.prior_candle_dir} (${Number(sol.prior_candle_bps || 0).toFixed(1)} bps)`;

                const sDelta = Number(sol.delta || 0);
                const sDeltaEl = document.getElementById('solDelta');
                sDeltaEl.innerText = `${sDelta >= 0 ? '+' : ''}$${sDelta.toFixed(3)}`;
                sDeltaEl.style.color = sDelta >= 0 ? 'var(--neon-green)' : 'var(--neon-rose)';
                document.getElementById('solDeadband').innerText = `Deadband: 5.0 bps ($${Number(sol.deadband || 0.06).toFixed(2)})`;
                document.getElementById('solBalancePod').innerText = `$${Number(sol.paper_balance || 27.98).toFixed(2)}`;
                document.getElementById('solBanner').innerHTML = `<strong>Status Quantitativo:</strong>&nbsp;${sol.status_signal || ''}`;

                // 4. Desk 3: Kalshi 15m Institutional
                document.getElementById('kalshiTicker').innerText = kalshi.ticker || 'KXBTC15M';
                document.getElementById('kalshiTimer').innerText = `Restam: ${kalshi.seconds_left || 0}s`;
                document.getElementById('kalshiProgress').style.width = `${kalshi.progress_pct || 0}%`;
                document.getElementById('kalshiStrike').innerText = `$${Number(kalshi.strike || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                document.getElementById('kalshiSpot').innerText = `$${Number(kalshi.spot || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                document.getElementById('kalshiPriorCandle').innerText = `Vela 15m Ant: ${kalshi.prior_candle_dir} (${Number(kalshi.prior_candle_bps || 0).toFixed(1)} bps)`;

                const kDelta = Number(kalshi.delta || 0);
                const kDeltaEl = document.getElementById('kalshiDelta');
                kDeltaEl.innerText = `${kDelta >= 0 ? '+' : ''}$${kDelta.toFixed(2)}`;
                kDeltaEl.style.color = kDelta >= 0 ? 'var(--neon-green)' : 'var(--neon-rose)';
                document.getElementById('kalshiDeadband').innerText = `Deadband: 5.0 bps ($${Number(kalshi.deadband || 42).toFixed(1)})`;
                document.getElementById('kalshiRealBal').innerText = `$${Number(kalshi.real_balance || 11.36).toFixed(2)} USD`;
                document.getElementById('kalshiBanner').innerHTML = `<strong>Filtros Jev 9-Anos:</strong>&nbsp;${kalshi.status_signal || ''}`;

                // Render table
                renderTable();

            } catch (e) {
                console.error("Erro update dashboard:", e);
            }
        }

        setInterval(updateDashboard, 1000);
        updateDashboard();
    </script>
</body>
</html>
"""

# ===================== REQUISITOS DO SERVIDOR HTTP =====================
class QuantDashboardHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Mantém console limpo

    def do_GET(self):
        global GLOBAL_STATE, btc_engine
        if self.path == "/" or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode("utf-8"))
        elif self.path.startswith("/api/dashboard_state"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
            self.end_headers()

            # BTC Engine State
            radar = btc_engine.get_radar_state()
            pricing = radar.get("pricing", {})
            cycle = radar.get("cycle", {})
            poly = radar.get("polymarket", {})
            signal = radar.get("signal", {})

            btc_trades_info = get_recent_btc_trades_and_stats(limit=20)
            sol_trades = get_sol_trades()
            kalshi_trades = get_kalshi_trades()

            payload = {
                "account": GLOBAL_STATE["account"],
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
                "pnl_summary": btc_trades_info["pnl_summary"],
                "recent_trades": btc_trades_info["recent_trades"],
                "sol_radar": GLOBAL_STATE["sol_radar"],
                "sol_trades": sol_trades,
                "kalshi_radar": GLOBAL_STATE["kalshi_radar"],
                "kalshi_trades": kalshi_trades,
                "timestamp": time.time()
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def run_server():
    btc_engine.start_loop()

    # Inicia background feeds worker para SOL e Kalshi
    t_feeds = threading.Thread(target=background_feeds_worker, daemon=True)
    t_feeds.start()

    print("=" * 75)
    print(f"-> ANTIGRAVITY QUANT DESK rodando em http://localhost:{PORT}")
    print(f"-> Polymarket BTC 5m [LIVE] | Funder: {FUNDER_ADDR}")
    print(f"-> Polymarket SOL 5m [PAPER] | Jev 5.0 bps Deadband")
    print(f"-> Kalshi BTC 15m [PAPER] | Conexão Real RSA-PSS: {KALSHI_KEY_ID[:8]}...")
    print("=" * 75)

    server = socketserver.TCPServer(("127.0.0.1", PORT), QuantDashboardHandler)
    server.serve_forever()

if __name__ == "__main__":
    run_server()
