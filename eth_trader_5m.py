"""
=============================================================================
ETHEREUM 5-MINUTE ALGO TRADER (POLYMARKET eth-updown-5m) — MODO PAPER
=============================================================================
- Exchange: Polymarket CLOB — Série Oficial: eth-updown-5m-{window_ts}
- Protocolo: Polymarket Gamma API REST + CLOB L2 Order Book API
- Frequência: Ciclos de 5 Minutos (300 segundos)
- Ponto de Avaliação Quantitativa: 135s (2m15s da vela de 5m / 45% do ciclo)
- Estratégia Quantitativa:
  * Deadband Dinâmico: 8.0 bps ($2.40 em $3,000 ETH)
  * Microprice Ponderado L2 & Order Book Imbalance (Stoikov Microstructure)
  * Teto de Preço Sniper: $0.55 (PRIMARY_MAX_PRICE) e Piso $0.35 (PRIMARY_MIN_PRICE)
  * Bússola Macro BTC: Lead-Lag e Confirmação de Momentum do Bitcoin
  * Filtro Jev Trend Continuation (Alinhamento com vela de 5m anterior da Binance)
  * Take-Profit Antecipado (SirMartingale): Venda com lucro se Best Bid bater >= 86¢
  * Stop-Loss de Emergência: Liquidação antecipada se delta reverter
- Modo: PAPER HYPER-REALISTA (Consome livro L2 real da CLOB, valida liquidez e simula execução taker)
=============================================================================
"""

import os
import sys
import time
import json
import urllib.request
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
import math
from risk_gate import (
    atomic_write_json,
    safe_read_json,
    check_pre_trade_gate,
    is_system_halted,
    validate_executable_edge_gate,
    compute_dynamic_stake,
    get_dynamic_deadband_gate,
    validate_clob_spread_gate
)
from execution_math import (
    calculate_vwap_ask,
    calculate_vwap_bid,
    calculate_executable_edge,
    compute_fractional_kelly_stake,
    bayesian_fair_value
)
from variable_bench import bench

# Garante suporte a UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from py_clob_client_v2 import (
    ClobClient,
    SignatureTypeV2,
    MarketOrderArgsV2,
    OrderType,
    BalanceAllowanceParams,
    AssetType
)
from py_clob_client_v2.order_builder.builder import ROUNDING_CONFIG

for _ts in ROUNDING_CONFIG:
    ROUNDING_CONFIG[_ts].amount = min(4, ROUNDING_CONFIG[_ts].amount)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
LIVE_STATE_JSON = os.path.join(BASE_DIR, "eth_live_market_state.json")

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
POLY_FUNDER_ADDRESS = ENV_CFG.get("POLY_FUNDER_ADDRESS", "0xE00Bd7989108c9016cCF4479ce03BaCa09f6314c")
POLY_PRIVATE_KEY_RAW = ENV_CFG.get("POLYGON_PRIVATE_KEY", "").strip()
POLYGON_PRIVATE_KEY = POLY_PRIVATE_KEY_RAW[2:] if POLY_PRIVATE_KEY_RAW.startswith("0x") else POLY_PRIVATE_KEY_RAW
ETH_MODE = ENV_CFG.get("ETH_MODE", "PAPER").upper()
JOURNAL_JSON = os.path.join(BASE_DIR, "eth_trading_journal.json")

# ===================== PARÂMETROS QUANTITATIVOS (JEV AI CALIBRATED) =====================
FIXED_STAKE = 1.00                # $1.00 por aposta
DEADBAND_BPS = 0.00080            # 8.0 bps (0.080%) do preço do ETH
DEADBAND_MIN_FLOOR = 1.80         # Piso mínimo de $1.80 de variação no ETH
PRIMARY_MAX_PRICE = 0.55          # Preço máximo de entrada (55¢)
PRIMARY_MIN_PRICE = 0.35          # Preço mínimo de entrada (35¢)
MAX_CLOB_SPREAD = 0.08            # Spread máximo aceito no book (8¢)
TAKE_PROFIT_PRICE = 0.86          # Take-Profit antecipado SirMartingale (86¢)
STOP_LOSS_MIN_BID = 0.15          # Preço mínimo para Stop-Loss antecipado (15¢)
EVAL_POINT_SEC = 135              # Ponto de decisão aos 135s (45% da vela)

PYTH_ETH_FEED_ID = "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace"

# ===================== ORÁCULOS E FEEDS SPOT =====================
def get_binance_eth_spot() -> Optional[float]:
    """Preço à vista do ETH/USDT na Binance"""
    url = "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2.5) as r:
            return float(json.loads(r.read().decode())["price"])
    except Exception:
        pass
    return None

def get_pyth_eth_spot() -> Optional[float]:
    """Preço à vista oficial do oráculo Pyth Network (ETH/USD)"""
    url = f"https://hermes.pyth.network/v2/updates/price/latest?ids%5B%5D={PYTH_ETH_FEED_ID}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2.5) as r:
            data = json.loads(r.read().decode())
            if "parsed" in data and len(data["parsed"]) > 0:
                p_info = data["parsed"][0]["price"]
                raw_price = float(p_info["price"])
                expo = int(p_info["expo"])
                return raw_price * (10 ** expo)
    except Exception:
        pass
    return None

def get_eth_spot_composite() -> Optional[float]:
    """Feed redundante: tenta Pyth Network primeiro, fallback para Binance"""
    p = get_pyth_eth_spot()
    if p and p > 100.0:
        return p
    return get_binance_eth_spot()

def get_eth_candle_open(window_ts: int) -> Optional[float]:
    """Abertura da vela de 5m de ETH correspondente ao window_ts"""
    url = f"https://api.binance.com/api/v3/klines?symbol=ETHUSDT&interval=5m&startTime={window_ts * 1000}&limit=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode())
            if data and len(data) > 0:
                return float(data[0][1])
    except Exception:
        pass
    return None

def get_eth_prior_candle() -> Optional[Dict[str, Any]]:
    """Vela de 5m anterior fechada na Binance para confirmação de momentum"""
    url = "https://api.binance.com/api/v3/klines?symbol=ETHUSDT&interval=5m&limit=2"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode())
            if len(data) >= 2:
                c = data[0]
                o, h, l, cl = float(c[1]), float(c[2]), float(c[3]), float(c[4])
                direction = "UP" if cl >= o else "DOWN"
                diff_bps = (abs(cl - o) / o) * 10000
                return {"direction": direction, "open": o, "close": cl, "diff_bps": round(diff_bps, 1)}
    except Exception:
        pass
    return None

def get_btc_macro_drift(window_ts: int) -> Optional[Dict[str, Any]]:
    """Bússola Macro do BTC (Lead-Lag): confirma se o mercado de cripto como um todo está alinhado"""
    url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&startTime={window_ts * 1000}&limit=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2.5) as r:
            data = json.loads(r.read().decode())
            if data and len(data) > 0:
                btc_open = float(data[0][1])
                btc_cur = float(data[0][4])
                btc_drift = btc_cur - btc_open
                btc_dir = "UP" if btc_drift >= 0 else "DOWN"
                return {"btc_open": btc_open, "btc_cur": btc_cur, "btc_drift": btc_drift, "btc_dir": btc_dir}
    except Exception:
        pass
    return None

# ===================== POLYMARKET CLOB & GAMMA API =====================
def get_polymarket_eth_market(window_ts: int) -> Optional[Dict[str, Any]]:
    """Busca o mercado oficial de Ethereum 5m na Gamma API da Polymarket"""
    slug = f"eth-updown-5m-{window_ts}"
    url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PolymarketEthPaperBot/2.0"})
        with urllib.request.urlopen(req, timeout=3.5) as r:
            data = json.loads(r.read().decode())
            if data and len(data) > 0:
                return data[0]
    except Exception:
        pass
    return None

def get_clob_orderbook(token_id: str) -> Optional[Dict[str, Any]]:
    """Consulta o Order Book L2 oficial na CLOB da Polymarket"""
    url = f"https://clob.polymarket.com/book?token_id={token_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PolymarketEthPaperBot/2.0"})
        with urllib.request.urlopen(req, timeout=3.0) as r:
            book = json.loads(r.read().decode())
            bids = [(float(b["price"]), float(b["size"])) for b in book.get("bids", []) if "price" in b and "size" in b and float(b["size"]) >= 1.0]
            asks = [(float(a["price"]), float(a["size"])) for a in book.get("asks", []) if "price" in a and "size" in a and float(a["size"]) >= 1.0]

            if not bids or not asks:
                return None

            best_bid_item = max(bids, key=lambda x: x[0])
            best_ask_item = min(asks, key=lambda x: x[0])

            best_bid, top_bid_size = best_bid_item[0], best_bid_item[1]
            best_ask, top_ask_size = best_ask_item[0], best_ask_item[1]

            spread = round(best_ask - best_bid, 4)
            mid_price = (best_bid + best_ask) / 2.0

            sum_bid_size = sum(sz for _, sz in bids)
            sum_ask_size = sum(sz for _, sz in asks)

            top_imbalance = (top_bid_size - top_ask_size) / (top_bid_size + top_ask_size) if (top_bid_size + top_ask_size) > 0 else 0.0
            depth_imbalance = (sum_bid_size - sum_ask_size) / (sum_bid_size + sum_ask_size) if (sum_bid_size + sum_ask_size) > 0 else 0.0

            if (top_bid_size + top_ask_size) > 0:
                microprice = (best_bid * top_ask_size + best_ask * top_bid_size) / (top_bid_size + top_ask_size)
            else:
                microprice = mid_price

            return {
                "best_bid": round(best_bid, 4),
                "best_ask": round(best_ask, 4),
                "spread": round(spread, 4),
                "mid_price": round(mid_price, 4),
                "top_bid_size": round(top_bid_size, 2),
                "top_ask_size": round(top_ask_size, 2),
                "sum_bid_size": round(sum_bid_size, 2),
                "sum_ask_size": round(sum_ask_size, 2),
                "top_imbalance": round(top_imbalance, 3),
                "depth_imbalance": round(depth_imbalance, 3),
                "microprice": round(microprice, 4),
                "bids_raw": bids,
                "asks_raw": asks
            }
    except Exception:
        return None

# ===================== ETHEREUM ALGO TRADER ENGINE (LIVE + PAPER) =====================
class EthereumTrader5M:
    def __init__(self):
        self.mode = ETH_MODE
        self.balance = 50.00 # Saldo inicial de referência paper
        self.trades = []
        self.current_open_position = None
        self.traded_windows = set()
        self.client: Optional[ClobClient] = None

        self.load_journal()

        if self.mode == "LIVE":
            if not POLY_PRIVATE_KEY:
                print("[!] AVISO: POLYGON_PRIVATE_KEY ausente. Alternando ETH para modo PAPER.")
                self.mode = "PAPER"
            else:
                try:
                    self.client = ClobClient(
                        host="https://clob.polymarket.com",
                        key=POLYGON_PRIVATE_KEY,
                        chain_id=137,
                        signature_type=SignatureTypeV2.POLY_GNOSIS_SAFE,
                        funder=POLY_FUNDER_ADDRESS
                    )
                    self.client.set_api_creds(self.client.create_or_derive_api_creds())
                    print(f"[*] ETH Desk 5m LIVE autenticado via Safe Funder: {POLY_FUNDER_ADDRESS}")
                except Exception as e:
                    print(f"[!] Erro ao inicializar ClobClient ETH: {e}. Alternando para PAPER.")
                    self.mode = "PAPER"

    def load_journal(self):
        if os.path.exists(JOURNAL_JSON):
            try:
                with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.current_open_position = data.get("open_position")
                    self.traded_windows = set(t.get("window_ts") for t in data.get("trades", []) if t.get("window_ts"))
                    self.balance = data.get("current_balance", 50.00)
            except Exception:
                pass

    def save_open_position(self, pos_data: dict):
        self.current_open_position = pos_data
        data = safe_read_json(JOURNAL_JSON, default={})
        if data:
            data["open_position"] = pos_data
            atomic_write_json(JOURNAL_JSON, data)

    def clear_open_position(self):
        self.current_open_position = None
        data = safe_read_json(JOURNAL_JSON, default={})
        if data:
            data["open_position"] = None
            atomic_write_json(JOURNAL_JSON, data)

    def update_live_state(self, state_dict: dict):
        atomic_write_json(LIVE_STATE_JSON, state_dict)

    def record_trade(self, trade_data: dict):
        journal = safe_read_json(JOURNAL_JSON, default={"mode": f"{self.mode}_ETH_5M", "current_balance": self.balance, "trades": []})
        journal["trades"] = journal.get("trades", [])
        journal["trades"].append(trade_data)
        journal["current_balance"] = self.balance
        wins = sum(1 for t in journal["trades"] if t.get("pnl", 0) >= 0)
        losses = sum(1 for t in journal["trades"] if t.get("pnl", 0) < 0)
        total = len(journal["trades"])
        journal["wins"] = wins
        journal["losses"] = losses
        journal["win_rate"] = round(wins / total * 100, 1) if total > 0 else 0.0

        atomic_write_json(JOURNAL_JSON, journal)

    def run_cycle(self):
        while True:
            try:
                now = time.time()
                window_ts = int(now // 300) * 300
                sec_in_window = int(now - window_ts)

                spot = get_eth_spot_composite()
                strike = get_eth_candle_open(window_ts)
                delta = (spot - strike) if (spot and strike) else 0.0
                deadband, eth_regime = get_dynamic_deadband_gate(strike or 3100.0, base_bps=DEADBAND_BPS, min_floor=DEADBAND_MIN_FLOOR, symbol="ETHUSDT")

                prior_candle = get_eth_prior_candle() or {}
                btc_macro = get_btc_macro_drift(window_ts) or {}

                state = {
                    "asset": "ETH",
                    "mode": self.mode,
                    "window_ts": window_ts,
                    "seconds_elapsed": sec_in_window,
                    "seconds_left": max(0, 300 - sec_in_window),
                    "progress_pct": round((sec_in_window / 300.0) * 100, 1),
                    "spot": spot or 0.0,
                    "strike": strike or 0.0,
                    "delta": round(delta, 3),
                    "deadband": round(deadband, 3),
                    "diurnal_regime": eth_regime.get("regime", "NEUTRAL"),
                    "deadband_mult": eth_regime.get("deadband_multiplier", 1.0),
                    "prior_candle_dir": prior_candle.get("direction", "NEUTRAL"),
                    "prior_candle_bps": prior_candle.get("diff_bps", 0.0),
                    "btc_macro_dir": btc_macro.get("btc_dir", "NEUTRAL"),
                    "btc_macro_drift": round(btc_macro.get("btc_drift", 0.0), 2),
                    "balance": round(self.balance, 2),
                    "has_open_position": bool(self.current_open_position)
                }

                # Monitoramento de Posição Aberta (Take-Profit & Stop-Loss)
                if self.current_open_position:
                    pos = self.current_open_position
                    token_id = pos.get("token_id")
                    target_side = pos.get("side")

                    book = get_clob_orderbook(token_id) if token_id else None
                    if book and sec_in_window >= 170:
                        best_bid = book["best_bid"]
                        # Take-Profit SirMartingale
                        if best_bid >= TAKE_PROFIT_PRICE:
                            payout = round(pos["contracts"] * best_bid, 4)
                            pnl = round(payout - pos["stake"], 4)
                            self.balance = round(self.balance + pnl, 4)
                            trade_rec = {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "window_ts": pos["window_ts"],
                                "slug": pos["slug"],
                                "target_side": target_side,
                                "strike": pos["strike"],
                                "final_spot": spot,
                                "result": "VITÓRIA (TAKE-PROFIT ANTECIPADO)",
                                "payout": payout,
                                "pnl": pnl,
                                "balance": self.balance
                            }
                            self.record_trade(trade_rec)
                            self.clear_open_position()
                            print(f"[ETH 5M] Take-Profit antecipado executado a ${best_bid:.2f} | PnL: +${pnl:.2f} USD")

                        # Stop-Loss Proativo
                        elif sec_in_window >= 200 and best_bid <= 0.35 and best_bid >= STOP_LOSS_MIN_BID:
                            adverse_delta = (delta < -deadband) if target_side == "UP" else (delta > deadband)
                            if adverse_delta:
                                payout = round(pos["contracts"] * best_bid, 4)
                                pnl = round(payout - pos["stake"], 4)
                                self.balance = round(self.balance + pnl, 4)
                                trade_rec = {
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "window_ts": pos["window_ts"],
                                    "slug": pos["slug"],
                                    "target_side": target_side,
                                    "strike": pos["strike"],
                                    "final_spot": spot,
                                    "result": "DEFESA (STOP-LOSS PROATIVO)",
                                    "payout": payout,
                                    "pnl": pnl,
                                    "balance": self.balance
                                }
                                self.record_trade(trade_rec)
                                self.clear_open_position()
                                print(f"[ETH 5M] Stop-Loss executado a ${best_bid:.2f} | Capital recuperado: ${payout:.2f}")

                # Avaliação de Nova Entrada (Janela 135s - 150s)
                elif sec_in_window >= EVAL_POINT_SEC and sec_in_window <= 150:
                    is_benched, bench_reason, bench_rem = bench.check_coin_flip_breaker("desk4", JOURNAL_JSON)
                    if not is_benched:
                        is_benched, bench_reason, bench_rem = bench.is_benched("desk4")
                    if is_benched:
                        print(f"   [🛑 VARIABLE BENCH]: Desk 4 em cooldown ({bench_reason}) — restam {bench_rem:.1f}s.")
                        state["status_signal"] = f"Bench Cooldown ({bench_reason}: {bench_rem:.0f}s)"
                        self.update_live_state(state)
                        time.sleep(5)
                        continue

                    if window_ts not in self.traded_windows and spot and strike:
                        mkt = get_polymarket_eth_market(window_ts)
                        if mkt:
                            tokens = json.loads(mkt.get("clobTokenIds", "[]")) if isinstance(mkt.get("clobTokenIds"), str) else mkt.get("clobTokenIds", [])
                            if len(tokens) >= 2:
                                token_up = tokens[0]
                                token_down = tokens[1]

                                target_side = None
                                target_token = None

                                # Filtro Deadband e Alinhamento
                                if delta >= deadband and prior_candle.get("direction") == "UP":
                                    target_side = "UP"
                                    target_token = token_up
                                elif delta <= -deadband and prior_candle.get("direction") == "DOWN":
                                    target_side = "DOWN"
                                    target_token = token_down

                                if target_side and target_token:
                                    book = get_clob_orderbook(target_token)
                                    if book:
                                        spread_ok, _, _ = validate_clob_spread_gate(
                                            spread=book.get("spread", 1.0),
                                            best_bid=book.get("best_bid", 0.0),
                                            best_ask=book.get("best_ask", 0.0),
                                            top_ask_size=book.get("top_ask_size", 0.0),
                                            target_stake_usd=FIXED_STAKE,
                                            max_tolerable_spread=0.050
                                        )
                                        if spread_ok:
                                            best_ask = book["best_ask"]
                                            if PRIMARY_MIN_PRICE <= best_ask <= PRIMARY_MAX_PRICE:
                                                # Pricing Black-Scholes + Bayesiano para ETH
                                                sec_left = max(1, 300 - sec_in_window)
                                                eff_vol = 0.45  # Volatilidade intra-vela de ETH (~45%)
                                                tau = max(1.0, float(sec_left)) / (365.25 * 24 * 3600)
                                                sig_sqrt_tau = eff_vol * math.sqrt(tau)
                                                d2 = (math.log(max(1.0, spot) / max(1.0, strike)) - 0.5 * (eff_vol ** 2) * tau) / max(1e-9, sig_sqrt_tau)
                                                bs_prob_up = 0.5 * (1.0 + math.erf(d2 / math.sqrt(2.0)))
                                                bs_fair = bs_prob_up if target_side == "UP" else (1.0 - bs_prob_up)

                                                p_sig = 0.65 if book.get("top_imbalance", 0) > 0.1 else (0.35 if book.get("top_imbalance", 0) < -0.1 else 0.50)
                                                model_fair_value = bayesian_fair_value(
                                                    prior_prob=bs_fair,
                                                    p_signal_if_outcome=p_sig if target_side == "UP" else (1.0 - p_sig),
                                                    p_signal_if_alternative=0.50,
                                                    collinearity_discount=0.75
                                                )

                                                # Dimensionamento por Kelly Fracionário (25% Kelly com Bounds Institucionais)
                                                cur_bankroll = max(20.0, self.balance)
                                                target_stake, kelly_status = compute_dynamic_stake(
                                                    bankroll=cur_bankroll,
                                                    win_probability=model_fair_value,
                                                    entry_price=best_ask,
                                                    fallback_stake=FIXED_STAKE,
                                                    kelly_fraction=0.25,
                                                    min_stake=1.00,
                                                    max_stake=2.50
                                                )

                                                if target_stake <= 0.0:
                                                    print(f"[*] [ETH 5M] [VETO KELLY]: {kelly_status}. Edge insuficiente.")
                                                    continue

                                                # VWAP na profundidade real do livro
                                                asks_raw = book.get("asks_raw", [])
                                                vwap_price, vwap_cost, vwap_shares, slip_bps = calculate_vwap_ask(asks_raw, target_usd=target_stake)

                                                if vwap_price is None:
                                                    print(f"[*] [ETH 5M] [VETO PROFUNDIDADE]: Livro raso! Profundidade (${vwap_cost:.2f}) insuficiente para ${target_stake:.2f}.")
                                                    continue

                                                # Validação Centralizada no RiskGate
                                                gate_ok, gate_msg = check_pre_trade_gate(
                                                    desk_id="DESK8_ETH_5M",
                                                    target_side=target_side,
                                                    stake=target_stake,
                                                    spot_price=spot,
                                                    strike_price=strike,
                                                    oracle_timestamp=time.time(),
                                                    current_balance=cur_bankroll,
                                                    execution_mode=self.mode,
                                                    fair_value=model_fair_value,
                                                    vwap_price=vwap_price,
                                                    min_net_edge=0.015
                                                )
                                                if not gate_ok:
                                                    print(f"[*] [ETH 5M] [RISK GATE VETO]: {gate_msg}")
                                                    continue

                                                exec_price = vwap_price

                                                # ── CÃO DE GUARDA JEV (Blindagem Anti-Exaustão e Anti-Repique ETH 5M) ──
                                                try:
                                                    from jev_microstructure_gate import jev_gate
                                                    clob_sp = book.get("spread", 0.03)
                                                    obi_val = book.get("top_imbalance", 0.0)
                                                    jev_res = jev_gate.evaluate_entry(
                                                        desk_id="desk8",
                                                        delta_usd=delta,
                                                        binance_drift=round(delta * 0.25, 2),
                                                        clob_spread=clob_sp,
                                                        contract_price=exec_price,
                                                        oracle_discrepancy=0.20,
                                                        seconds_left=int(sec_left),
                                                        obi=obi_val,
                                                        cvd=0.0,
                                                        deadband_threshold=deadband,
                                                        side=target_side,
                                                        symbol="ETH"
                                                    )
                                                    if jev_res.get("verdict") == "VETO":
                                                        print(f"[*] [ETH 5M] [🛑 VETO CÃO DE GUARDA JEV ETH]: {jev_res.get('veto_reason')} | Regime: {jev_res.get('candle_regime')}. Veto preventivo contra repique!")
                                                        continue
                                                except Exception as e:
                                                    print(f"[*] [ETH 5M] [!] Aviso Jev Gate ETH: {e}")

                                                is_maker_fill = False

                                                # Estratégia Maker Post-Only Inteligente (Touch Quoting JEV):
                                                # Se o spread for favorável (>= $0.02) e o touch estiver dentro do teto, cota 1 tick dentro do touch
                                                best_bid_eth = book.get("best_bid", 0.0)
                                                if book.get("spread", 0.0) >= 0.02 and best_bid_eth > 0 and (best_bid_eth + 0.01) <= PRIMARY_MAX_PRICE:
                                                    touch_price = round(best_bid_eth + 0.01, 3)
                                                    print(f"[*] [ETH 5M] [🎯 MAKER POST-ONLY JEV]: Cotando 1 tick dentro do touch a ${touch_price:.3f} (Bid: ${best_bid_eth:.3f} | VWAP Ask: ${vwap_price:.3f})")
                                                    exec_price = touch_price
                                                    is_maker_fill = True

                                                contracts = round(target_stake / exec_price, 4)
                                                pos_info = {
                                                    "window_ts": window_ts,
                                                    "slug": f"eth-updown-5m-{window_ts}",
                                                    "token_id": target_token,
                                                    "side": target_side,
                                                    "strike": strike,
                                                    "entry_price": exec_price,
                                                    "contracts": contracts,
                                                    "stake": target_stake,
                                                    "entry_time": datetime.now(timezone.utc).isoformat(),
                                                    "maker_fill": is_maker_fill
                                                }
                                                self.save_open_position(pos_info)
                                                self.traded_windows.add(window_ts)
                                                fill_tag = " [MAKER TOUCH FILL]" if is_maker_fill else " [TAKER VWAP FILL]"
                                                print(f"[*] [ETH 5M {self.mode}{fill_tag}] Ordem Executada: {target_side} a ${exec_price:.4f} ({contracts} cotas, stake ${target_stake:.2f})")
                                        else:
                                            print(f"[*] [ETH 5M] [SPREAD GATE VETO]: Spread fora da tolerância.")

                # Gestão Ativa da Posição (SirMartingale Take-Profit & Bonereaper Late-Window Salvage)
                if self.current_open_position and 150 <= sec_in_window <= 292:
                    pos = self.current_open_position
                    ob_manage = self.get_clob_orderbook(pos["token_id"])
                    if ob_manage:
                        cur_bid = ob_manage.get("best_bid", 0.0)

                        # 1. SirMartingale Take-Profit: Venda antecipada com lucro >= $0.86 aos 170s+
                        if cur_bid >= 0.86 and sec_in_window >= 170:
                            payout = round(pos["contracts"] * cur_bid, 4)
                            pnl = round(payout - pos["stake"], 4)
                            self.balance = round(self.balance + pnl, 4)
                            self.record_trade({
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "window_ts": pos["window_ts"],
                                "slug": pos["slug"],
                                "target_side": pos["side"],
                                "strike": pos["strike"],
                                "final_spot": spot,
                                "result": "VITÓRIA (TAKE-PROFIT)",
                                "payout": payout,
                                "pnl": pnl,
                                "balance": self.balance
                            })
                            self.clear_open_position()
                            print(f"[ETH 5M] Take-Profit Executado @ ${cur_bid:.2f}! PnL: +${pnl:.2f}")

                        # 2. Bonereaper Late-Window Salvage aos 255s-288s se Spot reverter contra nós
                        elif sec_in_window >= 255:
                            is_losing = (pos["side"] == "UP" and delta < -1.5) or (pos["side"] == "DOWN" and delta > 1.5)
                            if is_losing and cur_bid >= 0.15:
                                payout = round(pos["contracts"] * cur_bid, 4)
                                pnl = round(payout - pos["stake"], 4)
                                self.balance = round(self.balance + pnl, 4)
                                self.record_trade({
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "window_ts": pos["window_ts"],
                                    "slug": pos["slug"],
                                    "target_side": pos["side"],
                                    "strike": pos["strike"],
                                    "final_spot": spot,
                                    "result": "DEFESA (STOP-LOSS SALVAGE)",
                                    "payout": payout,
                                    "pnl": pnl,
                                    "balance": self.balance
                                })
                                self.clear_open_position()
                                print(f"[ETH 5M] Bonereaper Salvage Executado @ ${cur_bid:.2f}! Perda estancada em: ${pnl:.2f}")

                # Apuração no Final da Vela (295s - 299s)
                if self.current_open_position and sec_in_window >= 295:
                    pos = self.current_open_position
                    target_side = pos.get("side")
                    win = (delta >= 0) if target_side == "UP" else (delta < 0)
                    pnl = round(pos["contracts"] * 1.0 - pos["stake"], 4) if win else -pos["stake"]
                    payout = round(pos["contracts"] * 1.0, 4) if win else 0.0
                    self.balance = round(self.balance + pnl, 4)

                    trade_rec = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "window_ts": pos["window_ts"],
                        "slug": pos["slug"],
                        "target_side": target_side,
                        "strike": pos["strike"],
                        "final_spot": spot,
                        "result": "VITÓRIA" if win else "DERROTA",
                        "payout": payout,
                        "pnl": pnl,
                        "balance": self.balance
                    }
                    self.record_trade(trade_rec)
                    self.clear_open_position()
                    print(f"[ETH 5M] Apuração Final: {'VITÓRIA (+${pnl:.2f})' if win else f'DERROTA (-${abs(pnl):.2f})'}")

                self.update_live_state(state)
                time.sleep(2)

            except Exception as e:
                time.sleep(2)

def main():
    print("=" * 80)
    print("  🔷 INICIANDO DESK ETHEREUM 5M (POLYMARKET eth-updown-5m)")
    print(f"  Modo de Execução: {ETH_MODE} | Stake: ${FIXED_STAKE:.2f} USDC")
    print("  Deadband: 8.0 bps | Sweet-Spot: 135s | Lead-Lag Bússola BTC Ativa")
    print("=" * 80)
    trader = EthereumTrader5M()
    trader.run_cycle()

if __name__ == "__main__":
    main()
