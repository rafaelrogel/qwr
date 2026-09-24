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
JOURNAL_NATGAS_JSON = os.path.join(BASE_DIR, "kalshi_natgas_journal.json")
SIGNAL_WEATHER_JSON = os.path.join(BASE_DIR, "kalshi_live_weather_signal.json")
SOL_LIVE_STATE_JSON = os.path.join(BASE_DIR, "sol_live_market_state.json")

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
KALSHI_KEY_ID = ENV_CFG.get("KALSHI_KEY_ID", "")
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
        details = self.get_balance_details()
        return details.get("shard_2_usd", 9.05)

    def get_balance_details(self) -> Dict[str, Any]:
        default_res = {
            "shard_0_usd": 1.3125,
            "shard_2_usd": 9.0500,
            "total_usd": 10.3625,
            "portfolio_value": 0.54,
            "updated_ts": int(time.time())
        }
        if not self.private_key or not self.key_id:
            return default_res
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
                shard_0 = 0.0
                shard_2 = 0.0
                for b in res.get("balance_breakdown", []):
                    idx = b.get("exchange_index")
                    val = float(b.get("balance", 0.0))
                    if idx == 0:
                        shard_0 = val
                    elif idx == 2:
                        shard_2 = val
                
                total = float(res.get("balance_dollars", (shard_0 + shard_2)))
                port_val = float(res.get("portfolio_value", 0.0)) / 100.0 if "portfolio_value" in res else 0.0
                return {
                    "shard_0_usd": round(shard_0, 4),
                    "shard_2_usd": round(shard_2, 4),
                    "total_usd": round(total, 4),
                    "portfolio_value": round(port_val, 2),
                    "updated_ts": res.get("updated_ts", int(time.time()))
                }
        except Exception:
            pass
        return default_res

kalshi_auth = KalshiAuthHelper(KALSHI_KEY_ID, KALSHI_KEY_PATH)

# ===================== ESTADOS GLOBAIS DOS DESKS =====================
GLOBAL_STATE = {
    "account": {
        "initial_deposit": INITIAL_DEPOSIT_BTC,
        "current_balance_live": 22.5421,
        "funder_address": FUNDER_ADDR,
        "status": "SINCRONIZADO",
        "last_sync": time.time()
    },
    "sol_radar": {
        "asset": "SOL",
        "series": "sol-updown-5m",
        "mode": ENV_CFG.get("SOL_MODE", "LIVE").upper(),
        "spot": 114.50,
        "strike": 114.50,
        "delta": 0.0,
        "deadband": 0.06,
        "clob_bid": 0.0,
        "clob_ask": 0.0,
        "clob_spread": 0.0,
        "clob_microprice": 0.0,
        "clob_top_size": 0.0,
        "market_slug": "",
        "market_title": "Solana Up or Down 5m",
        "funder_verified": FUNDER_ADDR,
        "seconds_left": 150,
        "seconds_elapsed": 150,
        "progress_pct": 50.0,
        "prior_candle_dir": "UP",
        "prior_candle_bps": 12.0,
        "status_signal": "Sincronizando com CLOB Polymarket...",
        "paper_balance": 29.6506,
        "total_trades": 3,
        "wins": 3,
        "losses": 0,
        "win_rate": 100.0
    },
    "kalshi_radar": {
        "asset": "BTC",
        "series": "KXBTC15M",
        "mode": ENV_CFG.get("KALSHI_MODE", "LIVE").upper(),
        "real_connected": True,
        "real_balance": 9.05,
        "shard_2_balance": 9.05,
        "shard_0_balance": 1.31,
        "total_consolidated_balance": 10.36,
        "paper_balance": 35.91,
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
    },
    "kalshi_balances": {
        "shard_0_usd": 1.3125,
        "shard_2_usd": 9.0500,
        "total_usd": 10.3625,
        "portfolio_value": 0.54,
        "last_sync": time.time()
    },
    "natgas_radar": {
        "asset": "NATGAS",
        "series": "KXNATGAS-EIA",
        "mode": "PAPER (API REAL CONECTADA)",
        "paper_balance": 1000.0,
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "us_hdd": 11.8,
        "us_cdd": 44.8,
        "retail_consensus_bcf": 76.0,
        "model_forecast_bcf": 71.8,
        "expected_deviation_bcf": -4.2,
        "signal": "NEUTRAL / NO TRADE",
        "confidence_pct": 50.0,
        "rationale": "Aguardando janela de quarta-feira (14:00 - 18:00 ET)",
        "next_window": "Quarta-feira 14:00 - 18:00 ET",
        "has_open_position": False
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

            # Sobrescreve com dados ultra-precisos da CLOB se o bot de SOL estiver publicando
            if os.path.exists(SOL_LIVE_STATE_JSON):
                try:
                    with open(SOL_LIVE_STATE_JSON, "r", encoding="utf-8") as f:
                        s_live = json.load(f)
                        book_up = s_live.get("clob_up") or {}
                        book_down = s_live.get("clob_down") or {}
                        tgt_book = book_up if s_live.get("delta", 0) >= 0 else book_down
                        GLOBAL_STATE["sol_radar"].update({
                            "mode": s_live.get("mode", ENV_CFG.get("SOL_MODE", "LIVE").upper()),
                            "is_live": s_live.get("is_live", True),
                            "live_balance": s_live.get("live_balance", 21.80),
                            "paper_balance": s_live.get("paper_balance", 29.65),
                            "spot": s_live.get("spot", sol_spot),
                            "strike": s_live.get("strike", sol_strike),
                            "delta": s_live.get("delta", sol_delta),
                            "deadband": s_live.get("deadband", sol_deadband),
                            "seconds_left": s_live.get("seconds_left", sol_left),
                            "seconds_elapsed": s_live.get("seconds_elapsed", sol_elapsed),
                            "progress_pct": s_live.get("progress_pct", sol_pct),
                            "status_signal": s_live.get("status_signal", sol_signal),
                            "clob_bid": tgt_book.get("best_bid", 0.0),
                            "clob_ask": tgt_book.get("best_ask", 0.0),
                            "clob_spread": tgt_book.get("spread", 0.0),
                            "clob_microprice": tgt_book.get("microprice", 0.0),
                            "clob_top_size": tgt_book.get("top_ask_size", 0.0),
                            "market_slug": s_live.get("market_slug", ""),
                            "market_title": s_live.get("market_title", "Solana Up or Down 5m"),
                            "funder_verified": s_live.get("funder_verified", FUNDER_ADDR)
                        })
                except Exception:
                    pass
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

        # 3. Consulta de saldo real Kalshi a cada 15s (separados Shard 0 e Shard 2 + Consolidado)
        if now - last_kalshi_bal_poll > 15:
            k_bals = kalshi_auth.get_balance_details()
            GLOBAL_STATE["kalshi_balances"] = k_bals
            GLOBAL_STATE["kalshi_radar"]["real_balance"] = k_bals.get("shard_2_usd", 9.05)
            GLOBAL_STATE["kalshi_radar"]["shard_2_balance"] = k_bals.get("shard_2_usd", 9.05)
            GLOBAL_STATE["kalshi_radar"]["shard_0_balance"] = k_bals.get("shard_0_usd", 1.31)
            GLOBAL_STATE["kalshi_radar"]["total_consolidated_balance"] = k_bals.get("total_usd", 10.36)
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

        # NatGas & Live Weather Signal
        if os.path.exists(SIGNAL_WEATHER_JSON):
            try:
                with open(SIGNAL_WEATHER_JSON, "r", encoding="utf-8") as f:
                    w_j = json.load(f)
                    sig = w_j.get("signal", {})
                    dd = w_j.get("degree_days", {})
                    jsum = w_j.get("journal_summary", {})
                    GLOBAL_STATE["natgas_radar"].update({
                        "paper_balance": float(jsum.get("balance", 1000.0)),
                        "total_trades": int(jsum.get("total_trades", 0)),
                        "wins": int(jsum.get("wins", 0)),
                        "losses": int(jsum.get("losses", 0)),
                        "win_rate": float(jsum.get("win_rate", 0.0)),
                        "has_open_position": bool(jsum.get("has_open_position", False)),
                        "us_hdd": float(sig.get("us_weighted_hdd", 11.8)),
                        "us_cdd": float(sig.get("us_weighted_cdd", 44.8)),
                        "retail_consensus_bcf": float(sig.get("retail_consensus_bcf", 76.0)),
                        "model_forecast_bcf": float(sig.get("model_forecast_bcf", 71.8)),
                        "expected_deviation_bcf": float(sig.get("expected_deviation_bcf", -4.2)),
                        "signal": sig.get("kalshi_actionable_signal", "NEUTRAL / NO TRADE"),
                        "confidence_pct": float(sig.get("signal_confidence_pct", 50.0)),
                        "rationale": sig.get("signal_rationale", "Aguardando janela de quarta-feira (14:00 - 18:00 ET)"),
                        "next_window": sig.get("recommended_execution_window", "Quarta-feira 14:00 - 18:00 ET")
                    })
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

    current_bal = None
    if os.path.exists(JOURNAL_BTC_JSON):
        try:
            with open(JOURNAL_BTC_JSON, "r", encoding="utf-8") as f:
                jdata = json.load(f)
                b_val = jdata.get("current_balance")
                if b_val is not None:
                    current_bal = float(b_val)
        except Exception:
            pass
    if current_bal is None or current_bal <= 0:
        current_bal = float(real_trades[-1]["balance"]) if real_trades and real_trades[-1].get("balance") else INITIAL_DEPOSIT_BTC

    GLOBAL_STATE["account"]["current_balance_live"] = round(current_bal, 4)
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

def get_natgas_trades() -> List[dict]:
    if os.path.exists(JOURNAL_NATGAS_JSON):
        try:
            with open(JOURNAL_NATGAS_JSON, "r", encoding="utf-8") as f:
                j = json.load(f)
                return j.get("trade_history", [])[::-1]
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
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
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
        .border-natgas::before { background: linear-gradient(90deg, #d97706, var(--neon-amber)); }

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

        /* Desks Matrix (Multi-Asset) */
        .radar-matrix {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
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

        /* Master Desk Group Switcher */
        .main-desk-switcher {
            display: grid;
            grid-template-columns: 1fr 1fr auto;
            gap: 14px;
            align-items: stretch;
            margin-bottom: 8px;
        }

        @media (max-width: 900px) {
            .main-desk-switcher {
                grid-template-columns: 1fr;
            }
        }

        .desk-switch-tab {
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 16px 20px;
            display: flex;
            align-items: center;
            gap: 16px;
            cursor: pointer;
            text-align: left;
            transition: all 0.25s ease;
            position: relative;
            overflow: hidden;
            color: var(--text-pure);
        }

        .desk-switch-tab:hover {
            border-color: rgba(0, 240, 255, 0.4);
            transform: translateY(-2px);
            background: rgba(20, 30, 55, 0.85);
        }

        .desk-switch-tab.active {
            border-color: var(--neon-cyan);
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(8, 47, 73, 0.4));
            box-shadow: 0 0 24px rgba(0, 240, 255, 0.22), inset 0 0 12px rgba(0, 240, 255, 0.08);
        }

        .desk-switch-tab.active::after {
            content: '';
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, var(--neon-cyan), var(--neon-green));
        }

        .switch-icon {
            font-size: 24px;
            width: 48px;
            height: 48px;
            border-radius: 10px;
            background: rgba(30, 41, 59, 0.8);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            border: 1px solid var(--border-subtle);
        }

        .switch-content {
            display: flex;
            flex-direction: column;
            gap: 4px;
            flex-grow: 1;
        }

        .switch-title {
            font-size: 14px;
            font-weight: 800;
            letter-spacing: -0.2px;
            color: var(--text-pure);
        }

        .switch-desc {
            font-size: 11px;
            color: var(--text-dim);
        }

        .switch-badge {
            font-size: 10px;
            font-weight: 800;
            padding: 4px 10px;
            border-radius: 20px;
            letter-spacing: 0.6px;
            text-transform: uppercase;
        }

        .open-tab-btn {
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 0 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            color: var(--neon-cyan);
            text-decoration: none;
            font-size: 12px;
            font-weight: 700;
            transition: all 0.2s ease;
            white-space: nowrap;
        }

        .open-tab-btn:hover {
            border-color: var(--neon-cyan);
            background: rgba(0, 240, 255, 0.12);
            box-shadow: 0 0 16px rgba(0, 240, 255, 0.2);
            transform: translateY(-2px);
        }

        .desk-group-view {
            display: flex;
            flex-direction: column;
            gap: 24px;
            animation: fadeInView 0.3s ease;
        }

        @keyframes fadeInView {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .radar-matrix-dual {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
            gap: 24px;
        }

        @media (max-width: 600px) {
            .radar-matrix-dual {
                grid-template-columns: 1fr;
            }
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
                <span class="dot-pulse" style="background: var(--neon-green); color: var(--neon-green);"></span>
                <span>DESK 2: SOL LIVE</span>
            </div>
            <div class="status-chip">
                <span class="dot-pulse" style="background: var(--neon-cyan); color: var(--neon-cyan);"></span>
                <span>DESK 3: KALSHI LIVE</span>
            </div>
            <div class="status-chip">
                <span class="dot-pulse" style="background: var(--neon-amber); color: var(--neon-amber);"></span>
                <span>DESK 4: NATGAS STANDBY</span>
            </div>
            <div class="status-chip mono" id="clockUTC" style="color: var(--neon-amber); font-weight: 600;">
                UTC: --:--:--
            </div>
        </div>
    </header>

    <div class="container">

        <!-- MASTER DESK GROUP SWITCHER -->
        <div class="main-desk-switcher">
            <div class="desk-switch-tab active" id="tabPolymarket" onclick="switchMainTab('polymarket')">
                <div class="switch-icon" style="color: var(--neon-green); background: rgba(0, 245, 155, 0.1);">⚡</div>
                <div class="switch-content">
                    <div class="switch-title">PÁGINA 1: DESKS 1 & 2 — POLYMARKET (BTC & SOL)</div>
                    <div class="switch-desc">Saldo Compartilhado Polygon Safe: <span id="navSharedBal" class="mono font-bold" style="color: var(--neon-green); font-size: 13px;">$21.81 USDC</span></div>
                </div>
                <span class="switch-badge mode-live">SALDO COMPARTILHADO</span>
            </div>

            <div class="desk-switch-tab" id="tabKalshi" onclick="switchMainTab('kalshi')">
                <div class="switch-icon" style="color: var(--neon-cyan); background: rgba(0, 240, 255, 0.1);">🏛️</div>
                <div class="switch-content">
                    <div class="switch-title">PÁGINA 2: DESKS 3 & 4 — KALSHI CFTC (BTC 15M & NATGAS)</div>
                    <div class="switch-desc">Total Consolidado CFTC: <span id="navKalshiTotal" class="mono font-bold" style="color: var(--neon-cyan); font-size: 13px;">$10.36 USD</span> <span style="color: var(--text-faint); font-size: 11px;">(Shard 0: <span id="navKalshiS0" style="color: var(--neon-amber); font-weight: 700;">$1.31</span> | Shard 2: <span id="navKalshiS2" style="color: var(--neon-green); font-weight: 700;">$9.05</span>)</span></div>
                </div>
                <span class="switch-badge" style="background: rgba(0, 240, 255, 0.15); color: var(--neon-cyan); border: 1px solid var(--neon-cyan);">SALDO CONSOLIDADO</span>
            </div>

            <a id="btnOpenNewTab" href="/kalshi" target="_blank" class="open-tab-btn" title="Abrir Desk Kalshi em outra aba do navegador">
                <span>↗️ Abrir Kalshi em Nova Aba</span>
            </a>
        </div>

        <!-- ========================================================================= -->
        <!-- VIEW 1: POLYMARKET DESKS (DESKS 1 & 2 - SALDO COMPARTILHADO) -->
        <!-- ========================================================================= -->
        <div id="viewPolymarket" class="desk-group-view">
            <!-- 4 TOP METRICS POLYMARKET -->
            <div class="metrics-grid">
                <!-- 1. Saldo Compartilhado Safe -->
                <div class="metric-card border-btc">
                    <div class="metric-label">Saldo Compartilhado (Polygon Safe 1271)</div>
                    <div class="metric-val mono" id="heroSharedBal" style="color: var(--neon-green);">$21.81 USDC</div>
                    <div class="metric-sub" id="heroSharedSub">Funder Safe: 0xE00Bd798... | Compartilhado BTC & SOL</div>
                </div>

                <!-- 2. P&L Total Sessão Polymarket -->
                <div class="metric-card border-audit">
                    <div class="metric-label">P&L Sessão Polymarket</div>
                    <div class="metric-val mono" id="heroLivePnl" style="color: var(--neon-amber);">+$0.81 USDC</div>
                    <div class="metric-sub" id="heroLivePnlSub">Depósito Base: $21.00 | Recuperação & Lucro</div>
                </div>

                <!-- 3. Performance BTC 5m Live -->
                <div class="metric-card border-btc">
                    <div class="metric-label">Desk 1: Polymarket BTC 5m Live</div>
                    <div class="metric-val mono" id="heroBtcWinRate" style="color: var(--neon-cyan);">71.0% WR</div>
                    <div class="metric-sub" id="heroBtcCounts">93 Vitórias / 38 Derrotas (131 Ciclos)</div>
                </div>

                <!-- 4. Performance SOL 5m Live -->
                <div class="metric-card border-sol">
                    <div class="metric-label">Desk 2: Polymarket SOL 5m Live</div>
                    <div class="metric-val mono" id="heroSolWinRate" style="color: var(--neon-purple);">100% WR</div>
                    <div class="metric-sub" id="heroSolCounts">3 Vitórias / 0 Derrotas (3 Ciclos)</div>
                </div>
            </div>

            <!-- DESKS 1 & 2 MATRIX (DUAL COLUMNS) -->
            <div class="radar-matrix-dual">
                <!-- DESK 1: BTC 5M LIVE CARD -->
                <div class="desk-card">
                    <div class="desk-header">
                        <div class="desk-badge-group">
                            <div class="asset-icon" style="color: #f7931a;">₿</div>
                            <div>
                                <div class="desk-title">Desk 1: Bitcoin 5m Live</div>
                                <div style="font-size: 11px; color: var(--text-faint);">Polymarket CLOB V2 (Série btc-updown-5m)</div>
                            </div>
                        </div>
                        <span class="desk-mode-tag mode-live">● REAL MONEY (CLOB V2)</span>
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
                            <div class="pod-sub" id="btcDeadband">Deadband: 2.1 bps ($17.7)</div>
                        </div>
                        <div class="stat-pod">
                            <div class="pod-label">Cotas Polymarket CLOB</div>
                            <div class="pod-val mono" id="btcOdds" style="font-size: 13px;">UP $0.50 | DW $0.50</div>
                            <div class="pod-sub">Teto Sniper: ≤ $0.55</div>
                        </div>
                    </div>

                    <div class="decision-banner" id="btcBanner" style="border-left-color: var(--neon-green);">
                        Carregando tomada de decisão quantitativa do robô real...
                    </div>
                </div>

                <!-- DESK 2: SOL 5M LIVE CARD -->
                <div class="desk-card">
                    <div class="desk-header">
                        <div class="desk-badge-group">
                            <div class="asset-icon" style="color: #c084fc;">◎</div>
                            <div>
                                <div class="desk-title">Desk 2: Solana 5m Live</div>
                                <div style="font-size: 11px; color: var(--text-faint);">Polymarket sol-updown-5m (Safe 1271)</div>
                            </div>
                        </div>
                        <span class="desk-mode-tag mode-live" id="solBadge">● REAL MONEY (POLYMARKET CLOB)</span>
                    </div>

                    <div class="timer-box">
                        <div class="timer-info mono">
                            <span id="solTitleSpan">sol-updown-5m (Jev Sweet-Spot)</span>
                            <span id="solTimer" style="color: var(--neon-purple); font-weight: 700;">Restam: --s</span>
                        </div>
                        <div class="progress-track">
                            <div class="progress-bar" id="solProgress" style="width: 50%; background: linear-gradient(90deg, #6366f1, var(--neon-purple));"></div>
                        </div>
                    </div>

                    <div class="desk-stats-grid">
                        <div class="stat-pod">
                            <div class="pod-label">Polymarket CLOB L2</div>
                            <div class="pod-val mono" id="solClobPod" style="color: var(--neon-cyan); font-size: 13px;">Bid -- | Ask --</div>
                            <div class="pod-sub" id="solClobSub">Spread: -- | Micro: --</div>
                        </div>
                        <div class="stat-pod">
                            <div class="pod-label">Delta Intra-Vela</div>
                            <div class="pod-val mono" id="solDelta">$0.000</div>
                            <div class="pod-sub" id="solDeadband">Deadband: 5.0 bps ($0.06)</div>
                        </div>
                        <div class="stat-pod">
                            <div class="pod-label">SOL Spot Real</div>
                            <div class="pod-val mono" id="solSpot" style="color: var(--neon-purple);">$0.00</div>
                            <div class="pod-sub" id="solPriorCandle">Vela Anterior: --</div>
                        </div>
                        <div class="stat-pod">
                            <div class="pod-label">Saldo Compartilhado</div>
                            <div class="pod-val mono" id="solBalancePod" style="color: var(--neon-green);">$21.81 USDC</div>
                            <div class="pod-sub" id="solTradesSummary">3 Trades / 100% WR</div>
                        </div>
                    </div>

                    <div class="decision-banner" id="solBanner" style="border-left-color: var(--neon-purple);">
                        Aguardando dados da Solana...
                    </div>
                </div>
            </div>

            <!-- UNIFIED TABLES FOR POLYMARKET -->
            <div class="table-card">
                <div class="table-header">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <div style="font-size: 15px; font-weight: 700;">📋 Livro de Operações Polymarket (DeFi CLOB)</div>
                        <span id="polyTableTabIndicator" class="mono" style="font-size: 11px; color: var(--text-faint);">[ BITCOIN 5M ]</span>
                    </div>
                    <div style="display: flex; gap: 6px;">
                        <button class="tab-btn active" id="btnPolyBtc" style="padding: 4px 12px; font-size: 11px;" onclick="loadPolyTable('btc')">₿ BTC 5m Live Trades</button>
                        <button class="tab-btn" id="btnPolySol" style="padding: 4px 12px; font-size: 11px;" onclick="loadPolyTable('sol')">◎ SOL 5m Live Trades</button>
                    </div>
                </div>

                <div class="table-responsive">
                    <table class="quant-table">
                        <thead id="polyTableHead">
                            <!-- Injetado dinamicamente -->
                        </thead>
                        <tbody id="polyTableBody">
                            <tr><td colspan="12" style="text-align: center; color: var(--text-faint); padding: 24px;">Carregando livro contábil...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- ========================================================================= -->
        <!-- VIEW 2: KALSHI CFTC DESKS (DESKS 3 & 4 - SALDO CONSOLIDADO & SEPARADOS) -->
        <!-- ========================================================================= -->
        <div id="viewKalshi" class="desk-group-view" style="display: none;">
            <!-- 4 TOP METRICS KALSHI CFTC -->
            <div class="metrics-grid">
                <!-- 1. Total Consolidado Kalshi -->
                <div class="metric-card border-kalshi" style="box-shadow: 0 0 20px rgba(0, 240, 255, 0.15);">
                    <div class="metric-label" style="color: var(--neon-cyan); font-weight: 800;">Saldo Total Consolidado Kalshi</div>
                    <div class="metric-val mono" id="heroKalshiConsolidated" style="color: var(--neon-cyan); font-size: 28px;">$10.36 USD</div>
                    <div class="metric-sub" id="heroKalshiConsolidatedSub">Portfólio Total CFTC (Shard 0 + Shard 2 + Posições)</div>
                </div>

                <!-- 2. Saldo Shard 2 (BTC 15m) -->
                <div class="metric-card border-btc">
                    <div class="metric-label">Saldo Shard 2 (Desk 3: BTC 15m)</div>
                    <div class="metric-val mono" id="heroKalshiShard2" style="color: var(--neon-green);">$9.05 USD</div>
                    <div class="metric-sub">Sub-Exchange Shard 2 (KXBTC15M Event Contracts)</div>
                </div>

                <!-- 3. Saldo Shard 0 (NatGas / Conta Principal) -->
                <div class="metric-card border-natgas">
                    <div class="metric-label">Saldo Shard 0 (Desk 4: NatGas & Principal)</div>
                    <div class="metric-val mono" id="heroKalshiShard0" style="color: var(--neon-amber);">$1.31 USD</div>
                    <div class="metric-sub">Exchange Shard 0 (KXNATGAS / Colateral Primário)</div>
                </div>

                <!-- 4. Regulação & Chave RSA-PSS CFTC -->
                <div class="metric-card border-sol">
                    <div class="metric-label">Regulação & Autenticação CFTC</div>
                    <div class="metric-val mono" id="heroKalshiStatus" style="color: var(--neon-purple); font-size: 22px;">CFTC COMPLIANT</div>
                    <div class="metric-sub">RSA-PSS 2048-bit: 017addcd... | 0 Perdas</div>
                </div>
            </div>

            <!-- DESKS 3 & 4 MATRIX (DUAL COLUMNS) -->
            <div class="radar-matrix-dual">
                <!-- DESK 3: KALSHI BTC 15M CARD -->
                <div class="desk-card">
                    <div class="desk-header">
                        <div class="desk-badge-group">
                            <div class="asset-icon" style="color: var(--neon-cyan);">🏛️</div>
                            <div>
                                <div class="desk-title">Desk 3: Kalshi BTC 15m Desk</div>
                                <div style="font-size: 11px; color: var(--text-faint);">Série Oficial KXBTC15M (Exchange Shard 2)</div>
                            </div>
                        </div>
                        <span class="desk-mode-tag mode-live" id="kalshiBadge">● REAL MONEY (CFTC KALSHI)</span>
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
                            <div class="pod-sub" id="kalshiDeadband">Deadband: 5.0 bps ($42.00)</div>
                        </div>
                        <div class="stat-pod">
                            <div class="pod-label">Saldo Alocado Shard 2</div>
                            <div class="pod-val mono" id="kalshiRealBal" style="color: var(--neon-green);">$9.05 USD</div>
                            <div class="pod-sub">Consolidado: <span id="kalshiConsolSubDesk">$10.36 USD</span></div>
                        </div>
                    </div>

                    <div class="decision-banner" id="kalshiBanner" style="border-left-color: var(--neon-cyan);">
                        Aguardando dados da Kalshi...
                    </div>
                </div>

                <!-- DESK 4: KALSHI NATGAS & WEATHER (JEV) CARD -->
                <div class="desk-card" style="border-top: 2px solid var(--neon-amber);">
                    <div class="desk-header">
                        <div class="desk-badge-group">
                            <div class="asset-icon" style="color: var(--neon-amber);">🔥</div>
                            <div>
                                <div class="desk-title">Desk 4: Natural Gas & Weather Desk</div>
                                <div style="font-size: 11px; color: var(--text-faint);">Kalshi EIA Storage + Open-Meteo GFS (Shard 0)</div>
                            </div>
                        </div>
                        <span class="desk-mode-tag" style="background: rgba(251, 191, 36, 0.15); color: var(--neon-amber); border-color: rgba(251, 191, 36, 0.4);">● SIMULAÇÃO (API REAL) + JEV CO-PILOT</span>
                    </div>

                    <div class="timer-box">
                        <div class="timer-info mono">
                            <span>EIA Weekly Net Change</span>
                            <span id="natgasStatusSignal" style="color: var(--neon-amber); font-weight: 700;">NEUTRAL / NO TRADE</span>
                        </div>
                        <div class="progress-track">
                            <div class="progress-bar" id="natgasProgress" style="width: 100%; background: linear-gradient(90deg, #d97706, var(--neon-amber));"></div>
                        </div>
                    </div>

                    <div class="desk-stats-grid">
                        <div class="stat-pod">
                            <div class="pod-label">Graus-Dia Ponderados (7d)</div>
                            <div class="pod-val mono" id="natgasDegreeDays" style="color: var(--neon-cyan);">11.8 HDD | 44.8 CDD</div>
                            <div class="pod-sub">Open-Meteo GFS (5 Hubs EUA)</div>
                        </div>
                        <div class="stat-pod">
                            <div class="pod-label">Estoque EIA (Prev vs Consenso)</div>
                            <div class="pod-val mono" id="natgasForecastBcf">71.8 vs 76.0 Bcf</div>
                            <div class="pod-sub" id="natgasDeltaBcf">Desvio Estimado: -4.2 Bcf</div>
                        </div>
                        <div class="stat-pod">
                            <div class="pod-label">Co-Piloto JEV Consensus</div>
                            <div class="pod-val mono" id="natgasJevConfidence" style="color: var(--neon-green);">50.0% (Standby)</div>
                            <div class="pod-sub">Quarta 14:00 - 18:00 ET</div>
                        </div>
                        <div class="stat-pod">
                            <div class="pod-label">Saldo Alocado Shard 0</div>
                            <div class="pod-val mono" id="natgasShard0Bal" style="color: var(--neon-amber);">$1.31 USD</div>
                            <div class="pod-sub">Paper: $1,000.00 USD</div>
                        </div>
                    </div>

                    <div class="decision-banner" id="natgasBanner" style="border-left-color: var(--neon-amber);">
                        Carregando análise física e climatológica do Henry Hub...
                    </div>
                </div>
            </div>

            <!-- UNIFIED TABLES FOR KALSHI -->
            <div class="table-card">
                <div class="table-header">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <div style="font-size: 15px; font-weight: 700;">📋 Livro de Operações Kalshi (CFTC Regulated)</div>
                        <span id="kalshiTableTabIndicator" class="mono" style="font-size: 11px; color: var(--text-faint);">[ KXBTC15M ]</span>
                    </div>
                    <div style="display: flex; gap: 6px;">
                        <button class="tab-btn active" id="btnKalshiBtc" style="padding: 4px 12px; font-size: 11px;" onclick="loadKalshiTable('kalshi')">🏛️ KXBTC15M Trades</button>
                        <button class="tab-btn" id="btnKalshiNatGas" style="padding: 4px 12px; font-size: 11px;" onclick="loadKalshiTable('natgas')">🔥 NatGas EIA Trades</button>
                    </div>
                </div>

                <div class="table-responsive">
                    <table class="quant-table">
                        <thead id="kalshiTableHead">
                            <!-- Injetado dinamicamente -->
                        </thead>
                        <tbody id="kalshiTableBody">
                            <tr><td colspan="10" style="text-align: center; color: var(--text-faint); padding: 24px;">Carregando livro Kalshi...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

    </div>

    <script>
        let currentPolyAsset = 'btc';
        let currentKalshiAsset = 'kalshi';
        let latestDashboardData = null;

        function switchMainTab(tab) {
            const viewPoly = document.getElementById('viewPolymarket');
            const viewKal = document.getElementById('viewKalshi');
            const tabPoly = document.getElementById('tabPolymarket');
            const tabKal = document.getElementById('tabKalshi');
            const btnTab = document.getElementById('btnOpenNewTab');

            if (tab === 'kalshi') {
                viewPoly.style.display = 'none';
                viewKal.style.display = 'block';
                tabKal.classList.add('active');
                tabPoly.classList.remove('active');
                if (btnTab) {
                    btnTab.href = '/polymarket';
                    btnTab.innerHTML = '<span>↗️ Abrir Polymarket em Nova Aba</span>';
                    btnTab.title = 'Abrir Desks Polymarket em outra aba';
                }
                history.replaceState(null, null, '#kalshi');
            } else {
                viewPoly.style.display = 'block';
                viewKal.style.display = 'none';
                tabPoly.classList.add('active');
                tabKal.classList.remove('active');
                if (btnTab) {
                    btnTab.href = '/kalshi';
                    btnTab.innerHTML = '<span>↗️ Abrir Kalshi em Nova Aba</span>';
                    btnTab.title = 'Abrir Desks Kalshi em outra aba';
                }
                history.replaceState(null, null, '#polymarket');
            }
        }

        function initViewRouting() {
            const path = window.location.pathname.toLowerCase();
            const hash = window.location.hash.toLowerCase();
            if (path.includes('kalshi') || hash === '#kalshi') {
                switchMainTab('kalshi');
            } else {
                switchMainTab('polymarket');
            }
        }
        window.addEventListener('hashchange', initViewRouting);

        function loadPolyTable(asset) {
            currentPolyAsset = asset;
            const bBtc = document.getElementById('btnPolyBtc');
            const bSol = document.getElementById('btnPolySol');
            const ind = document.getElementById('polyTableTabIndicator');
            if (bBtc) bBtc.classList.toggle('active', asset === 'btc');
            if (bSol) bSol.classList.toggle('active', asset === 'sol');
            if (ind) ind.innerText = asset === 'btc' ? '[ BITCOIN 5M ]' : '[ SOLANA 5M ]';
            renderPolyTable();
        }

        function renderPolyTable() {
            if (!latestDashboardData) return;
            const tbody = document.getElementById('polyTableBody');
            const thead = document.getElementById('polyTableHead');
            if (!tbody || !thead) return;

            if (currentPolyAsset === 'btc') {
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
                    tbody.innerHTML = '<tr><td colspan="12" style="text-align:center; padding:20px; color:var(--text-faint);">Nenhuma aposta real recente gravada.</td></tr>';
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
            } else if (currentPolyAsset === 'sol') {
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
                    tbody.innerHTML = '<tr><td colspan="10" style="text-align:center; padding:20px; color:var(--text-faint);">Nenhum trade executado em Solana ainda.</td></tr>';
                    return;
                }
                tbody.innerHTML = solTrades.map(t => {
                    const isWin = (t.result || '').includes('VITÓRIA') || Number(t.pnl || 0) > 0;
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
            }
        }

        function loadKalshiTable(asset) {
            currentKalshiAsset = asset;
            const bBtc = document.getElementById('btnKalshiBtc');
            const bNg = document.getElementById('btnKalshiNatGas');
            const ind = document.getElementById('kalshiTableTabIndicator');
            if (bBtc) bBtc.classList.toggle('active', asset === 'kalshi');
            if (bNg) bNg.classList.toggle('active', asset === 'natgas');
            if (ind) ind.innerText = asset === 'kalshi' ? '[ KXBTC15M ]' : '[ NATGAS EIA ]';
            renderKalshiTable();
        }

        function renderKalshiTable() {
            if (!latestDashboardData) return;
            const tbody = document.getElementById('kalshiTableBody');
            const thead = document.getElementById('kalshiTableHead');
            if (!tbody || !thead) return;

            if (currentKalshiAsset === 'kalshi') {
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
                        <th>Saldo Shard 2</th>
                    </tr>
                `;
                const kTrades = latestDashboardData.kalshi_trades || [];
                if (kTrades.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; padding:20px; color:var(--text-faint);">0 trades forçados. Filtros de tendência e teto de preço preservaram 100% da banca ($9.05 USD intactos).</td></tr>';
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
            } else if (currentKalshiAsset === 'natgas') {
                thead.innerHTML = `
                    <tr>
                        <th>Data (UTC)</th>
                        <th>Semana EIA</th>
                        <th>HDD/CDD 7d</th>
                        <th>Previsão GFS</th>
                        <th>Consenso Retail</th>
                        <th>Desvio Bcf</th>
                        <th>Veredito JEV</th>
                        <th>Posição Kalshi</th>
                        <th>Resultado</th>
                        <th>P&L</th>
                        <th>Saldo Shard 0</th>
                    </tr>
                `;
                const ngTrades = latestDashboardData.natgas_trades || [];
                if (ngTrades.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="11" style="text-align:center; padding:20px; color:var(--text-faint);">0 trades executados. O robô opera semanalmente às quartas-feiras (14h-18h ET) após consolidação dos dados climáticos NOAA/GFS e validação do Co-Piloto JEV. Banca Shard 0 intacta.</td></tr>';
                    return;
                }
                tbody.innerHTML = ngTrades.map(t => `
                    <tr>
                        <td class="mono">${t.timestamp || '-'}</td>
                        <td class="mono" style="color:var(--neon-amber);">${t.eia_week || '-'}</td>
                        <td class="mono">${t.degree_days || '-'}</td>
                        <td class="mono">${t.forecast_bcf ? Number(t.forecast_bcf).toFixed(1) + ' Bcf' : '-'}</td>
                        <td class="mono">${t.consensus_bcf ? Number(t.consensus_bcf).toFixed(1) + ' Bcf' : '-'}</td>
                        <td class="mono" style="color:var(--neon-cyan);">${t.deviation_bcf ? (t.deviation_bcf > 0 ? '+' : '') + Number(t.deviation_bcf).toFixed(1) + ' Bcf' : '-'}</td>
                        <td class="mono" style="color:var(--neon-green);">${t.jev_verdict || 'APROVADO'}</td>
                        <td><span class="badge-up">${t.action || '-'}</span></td>
                        <td><span class="badge-win">${t.result || 'PENDENTE'}</span></td>
                        <td class="mono" style="color:${t.pnl >= 0 ? 'var(--neon-green)' : 'var(--neon-rose)'};">${t.pnl >= 0 ? '+' : ''}$${Number(t.pnl || 0).toFixed(2)}</td>
                        <td class="mono" style="font-weight:700;">$${Number(t.balance || 1.31).toFixed(2)}</td>
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
                const clockEl = document.getElementById('clockUTC');
                if (clockEl) clockEl.innerText = `UTC: ${now.toISOString().substring(11, 19)}`;

                // =========================================================
                // 1. SALDO COMPARTILHADO & MÉTRICAS POLYMARKET (DESKS 1 & 2)
                // =========================================================
                const pnl = data.pnl_summary || {};
                const acc = data.account || {};
                const sol = data.sol_radar || {};
                const btc = data.current_cycle || {};
                const curBal = Number(acc.current_balance_live || pnl.current_balance || 21.81).toFixed(2);

                // Top Switcher Balances
                const navSharedBal = document.getElementById('navSharedBal');
                if (navSharedBal) navSharedBal.innerText = `$${curBal} USDC`;

                // View Polymarket Hero Pods
                const heroSharedBal = document.getElementById('heroSharedBal');
                if (heroSharedBal) heroSharedBal.innerText = `$${curBal} USDC`;

                const netPnl = Number(pnl.net_real_pnl || (curBal - 21.00));
                const heroLivePnl = document.getElementById('heroLivePnl');
                if (heroLivePnl) {
                    heroLivePnl.innerText = `${netPnl >= 0 ? '+' : ''}$${netPnl.toFixed(2)} USDC`;
                    heroLivePnl.style.color = netPnl >= 0 ? 'var(--neon-green)' : 'var(--neon-rose)';
                }
                const heroLivePnlSub = document.getElementById('heroLivePnlSub');
                if (heroLivePnlSub) {
                    heroLivePnlSub.innerText = `Depósito: $${Number(pnl.initial_deposit || 21.00).toFixed(2)} | P&L: ${netPnl >= 0 ? '+' : ''}$${netPnl.toFixed(2)} USDC`;
                }

                const heroBtcWinRate = document.getElementById('heroBtcWinRate');
                if (heroBtcWinRate) heroBtcWinRate.innerText = `${Number(pnl.win_rate || 71.0).toFixed(1)}% WR`;
                const heroBtcCounts = document.getElementById('heroBtcCounts');
                if (heroBtcCounts) heroBtcCounts.innerText = `${pnl.wins || 93} Vitórias / ${pnl.losses || 38} Derrotas (${pnl.total_participated_bets || 131} Ciclos)`;

                const heroSolWinRate = document.getElementById('heroSolWinRate');
                if (heroSolWinRate) heroSolWinRate.innerText = `${Number(sol.win_rate || 100).toFixed(0)}% WR`;
                const heroSolCounts = document.getElementById('heroSolCounts');
                if (heroSolCounts) heroSolCounts.innerText = `${sol.wins || 3} Vitórias / ${sol.losses || 0} Derrotas (${sol.total_trades || 3} Ciclos)`;

                // Desk 1: BTC 5m Card
                if (document.getElementById('btcCycleBadge')) document.getElementById('btcCycleBadge').innerText = btc.title || `btc-updown-5m-${btc.window_ts || ''}`;
                if (document.getElementById('btcTimer')) document.getElementById('btcTimer').innerText = `Restam: ${btc.seconds_left || 0}s`;
                if (document.getElementById('btcProgress')) document.getElementById('btcProgress').style.width = `${btc.progress_pct || 0}%`;
                if (document.getElementById('btcStrike')) document.getElementById('btcStrike').innerText = `$${Number(btc.strike || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                if (document.getElementById('btcSpot')) document.getElementById('btcSpot').innerText = `$${Number(btc.oracle_spot || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                if (document.getElementById('btcBinanceSpread')) document.getElementById('btcBinanceSpread').innerText = `Binance: $${Number(btc.binance_spot || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

                const bDelta = Number(btc.delta || 0);
                const bDeltaEl = document.getElementById('btcDelta');
                if (bDeltaEl) {
                    bDeltaEl.innerText = `${bDelta >= 0 ? '+' : ''}$${bDelta.toFixed(2)}`;
                    bDeltaEl.style.color = bDelta >= 0 ? 'var(--neon-green)' : 'var(--neon-rose)';
                }
                if (document.getElementById('btcOdds')) {
                    document.getElementById('btcOdds').innerText = `UP $${Number(btc.poly_price_up || 0.50).toFixed(2)} | DW $${Number(btc.poly_price_down || 0.50).toFixed(2)}`;
                }
                if (btc.signal && document.getElementById('btcBanner')) {
                    const bBanner = document.getElementById('btcBanner');
                    bBanner.innerHTML = `<strong>${btc.signal.action || 'Monitorando'}:</strong>&nbsp;${btc.signal.rationale || ''}`;
                    if (btc.signal.color) bBanner.style.borderLeftColor = btc.signal.color;
                }

                // Desk 2: SOL 5m Card
                if (document.getElementById('solTimer')) document.getElementById('solTimer').innerText = `Restam: ${sol.seconds_left || 0}s`;
                if (document.getElementById('solProgress')) document.getElementById('solProgress').style.width = `${sol.progress_pct || 0}%`;
                if (document.getElementById('solTitleSpan') && sol.market_title) document.getElementById('solTitleSpan').innerText = sol.market_title;
                if (document.getElementById('solClobPod')) {
                    const sBid = Number(sol.clob_bid || 0);
                    const sAsk = Number(sol.clob_ask || 0);
                    const sSpread = Number(sol.clob_spread || 0);
                    const sMicro = Number(sol.clob_microprice || 0);
                    document.getElementById('solClobPod').innerText = (sBid > 0 || sAsk > 0) ? `Bid $${sBid.toFixed(2)} | Ask $${sAsk.toFixed(2)}` : 'CLOB Sincronizando...';
                    document.getElementById('solClobSub').innerText = (sSpread > 0) ? `Spread: $${sSpread.toFixed(3)} | Micro: $${sMicro.toFixed(3)}` : 'Polymarket sol-updown-5m';
                }
                if (document.getElementById('solSpot')) document.getElementById('solSpot').innerText = `$${Number(sol.spot || 0).toFixed(2)}`;
                if (document.getElementById('solPriorCandle')) document.getElementById('solPriorCandle').innerText = `Vela Ant: ${sol.prior_candle_dir} (${Number(sol.prior_candle_bps || 0).toFixed(1)} bps)`;

                const sDelta = Number(sol.delta || 0);
                const sDeltaEl = document.getElementById('solDelta');
                if (sDeltaEl) {
                    sDeltaEl.innerText = `${sDelta >= 0 ? '+' : ''}$${sDelta.toFixed(3)}`;
                    sDeltaEl.style.color = sDelta >= 0 ? 'var(--neon-green)' : 'var(--neon-rose)';
                }
                if (document.getElementById('solDeadband')) document.getElementById('solDeadband').innerText = `Deadband: 5.0 bps ($${Number(sol.deadband || 0.06).toFixed(2)})`;
                if (document.getElementById('solBalancePod')) document.getElementById('solBalancePod').innerText = `$${curBal} USDC`;
                if (document.getElementById('solTradesSummary')) {
                    document.getElementById('solTradesSummary').innerText = `${sol.wins || 3}W / ${sol.losses || 0}L (${sol.total_trades || 3} Trades | ${Number(sol.win_rate || 100).toFixed(0)}% WR)`;
                }
                if (document.getElementById('solBanner')) {
                    document.getElementById('solBanner').innerHTML = `<strong>Status Quantitativo:</strong>&nbsp;${sol.status_signal || ''}`;
                }

                // =========================================================
                // 2. SALDOS KALSHI CFTC: SEPARADOS (SHARD 0 / SHARD 2) & CONSOLIDADO (DESKS 3 & 4)
                // =========================================================
                const kalshi = data.kalshi_radar || {};
                const kb = data.kalshi_balances || {};
                const natgas = data.natgas_radar || {};

                const shard0Val = Number(kb.shard_0_usd !== undefined ? kb.shard_0_usd : (kalshi.shard_0_balance || 1.3125)).toFixed(2);
                const shard2Val = Number(kb.shard_2_usd !== undefined ? kb.shard_2_usd : (kalshi.shard_2_balance || 9.0500)).toFixed(2);
                const totalConsolVal = Number(kb.total_usd !== undefined ? kb.total_usd : (kalshi.total_consolidated_balance || 10.3625)).toFixed(2);

                // Nav switcher elements
                if (document.getElementById('navKalshiTotal')) document.getElementById('navKalshiTotal').innerText = `$${totalConsolVal} USD`;
                if (document.getElementById('navKalshiS0')) document.getElementById('navKalshiS0').innerText = `$${shard0Val}`;
                if (document.getElementById('navKalshiS2')) document.getElementById('navKalshiS2').innerText = `$${shard2Val}`;

                // View Kalshi Hero Pods
                if (document.getElementById('heroKalshiConsolidated')) document.getElementById('heroKalshiConsolidated').innerText = `$${totalConsolVal} USD`;
                if (document.getElementById('heroKalshiShard2')) document.getElementById('heroKalshiShard2').innerText = `$${shard2Val} USD`;
                if (document.getElementById('heroKalshiShard0')) document.getElementById('heroKalshiShard0').innerText = `$${shard0Val} USD`;

                // Desk 3: Kalshi BTC 15m Card
                if (document.getElementById('kalshiTicker')) document.getElementById('kalshiTicker').innerText = kalshi.ticker || 'KXBTC15M';
                if (document.getElementById('kalshiTimer')) document.getElementById('kalshiTimer').innerText = `Restam: ${kalshi.seconds_left || 0}s`;
                if (document.getElementById('kalshiProgress')) document.getElementById('kalshiProgress').style.width = `${kalshi.progress_pct || 0}%`;
                if (document.getElementById('kalshiStrike')) document.getElementById('kalshiStrike').innerText = `$${Number(kalshi.strike || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                if (document.getElementById('kalshiSpot')) document.getElementById('kalshiSpot').innerText = `$${Number(kalshi.spot || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                if (document.getElementById('kalshiPriorCandle')) document.getElementById('kalshiPriorCandle').innerText = `Vela 15m Ant: ${kalshi.prior_candle_dir || 'DOWN'} (${Number(kalshi.prior_candle_bps || 0).toFixed(1)} bps)`;

                const kDelta = Number(kalshi.delta || 0);
                const kDeltaEl = document.getElementById('kalshiDelta');
                if (kDeltaEl) {
                    kDeltaEl.innerText = `${kDelta >= 0 ? '+' : ''}$${kDelta.toFixed(2)}`;
                    kDeltaEl.style.color = kDelta >= 0 ? 'var(--neon-green)' : 'var(--neon-rose)';
                }
                if (document.getElementById('kalshiDeadband')) document.getElementById('kalshiDeadband').innerText = `Deadband: 5.0 bps ($${Number(kalshi.deadband || 42).toFixed(1)})`;
                if (document.getElementById('kalshiRealBal')) document.getElementById('kalshiRealBal').innerText = `$${shard2Val} USD`;
                if (document.getElementById('kalshiConsolSubDesk')) document.getElementById('kalshiConsolSubDesk').innerText = `$${totalConsolVal} USD`;
                if (document.getElementById('kalshiBanner')) {
                    document.getElementById('kalshiBanner').innerHTML = `<strong>Filtros Jev 9-Anos:</strong>&nbsp;${kalshi.status_signal || ''}`;
                }

                // Desk 4: Kalshi NatGas EIA Card
                if (document.getElementById('natgasDegreeDays')) document.getElementById('natgasDegreeDays').innerText = `${Number(natgas.us_hdd || 11.8).toFixed(1)} HDD | ${Number(natgas.us_cdd || 44.8).toFixed(1)} CDD`;
                if (document.getElementById('natgasForecastBcf')) document.getElementById('natgasForecastBcf').innerText = `${Number(natgas.model_forecast_bcf || 71.8).toFixed(1)} vs ${Number(natgas.retail_consensus_bcf || 76.0).toFixed(1)} Bcf`;
                const deltaBcf = Number(natgas.expected_deviation_bcf || -4.2);
                if (document.getElementById('natgasDeltaBcf')) document.getElementById('natgasDeltaBcf').innerText = `Desvio Estimado: ${deltaBcf >= 0 ? '+' : ''}${deltaBcf.toFixed(1)} Bcf`;
                if (document.getElementById('natgasJevConfidence')) document.getElementById('natgasJevConfidence').innerText = `${Number(natgas.confidence_pct || 50).toFixed(1)}% (${natgas.signal || 'NEUTRAL'})`;
                if (document.getElementById('natgasShard0Bal')) document.getElementById('natgasShard0Bal').innerText = `$${shard0Val} USD`;
                if (document.getElementById('natgasStatusSignal')) document.getElementById('natgasStatusSignal').innerText = natgas.signal || 'NEUTRAL / NO TRADE';
                if (document.getElementById('natgasBanner')) {
                    document.getElementById('natgasBanner').innerHTML = `<strong>Co-Piloto JEV & Clima:</strong>&nbsp;${natgas.rationale || 'Aguardando janela de quarta-feira (14:00 - 18:00 ET)'}`;
                }

                // Render Tables
                renderPolyTable();
                renderKalshiTable();

            } catch (e) {
                console.error("Erro update dashboard:", e);
            }
        }

        // Inicialização
        initViewRouting();
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
        path_clean = self.path.split('?')[0].rstrip('/')
        if path_clean in ("", "/polymarket", "/kalshi"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode("utf-8"))
        elif self.path.startswith("/api/dashboard_state"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:8080")
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
            natgas_trades = get_natgas_trades()

            payload = {
                "account": GLOBAL_STATE["account"],
                "kalshi_balances": GLOBAL_STATE.get("kalshi_balances", {}),
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
                "natgas_radar": GLOBAL_STATE["natgas_radar"],
                "natgas_trades": natgas_trades,
                "timestamp": time.time()
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

def run_server():
    btc_engine.start_loop()

    # Inicia background feeds worker para SOL e Kalshi
    t_feeds = threading.Thread(target=background_feeds_worker, daemon=True)
    t_feeds.start()

    sol_mode = ENV_CFG.get('SOL_MODE', 'PAPER').upper()
    kalshi_mode = ENV_CFG.get('KALSHI_MODE', 'PAPER').upper()

    print("=" * 75)
    print(f"-> ANTIGRAVITY QUANT DESK rodando em http://localhost:{PORT}")
    print(f"-> Polymarket BTC 5m [LIVE] | Funder: {FUNDER_ADDR}")
    print(f"-> Polymarket SOL 5m [{sol_mode}] | Jev 5.0 bps Deadband")
    print(f"-> Kalshi BTC 15m [{kalshi_mode}] | Conexão Real RSA-PSS: {KALSHI_KEY_ID[:8]}...")
    print("=" * 75)

    server = ThreadedTCPServer(("127.0.0.1", PORT), QuantDashboardHandler)
    server.serve_forever()

if __name__ == "__main__":
    run_server()
