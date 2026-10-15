"""
=============================================================================
SOLANA 5-MINUTE ALGO TRADER (POLYMARKET sol-updown-5m) — MODO PAPER COM API REAL
=============================================================================
- Exchange: Polymarket CLOB — Série Oficial: sol-updown-5m-{window_ts}
- Protocolo: Polymarket Gamma API REST + CLOB L2 Order Book API
- Frequência: Ciclos de 5 Minutos (300 segundos)
- Ponto de Avaliação Quantitativa: 135s (2m15s da vela de 5m / 45% do ciclo)
- Estratégia Quantitativa:
  * Deadband Dinâmico: 5.0 bps (Jev Sweet-Spot, min floor $0.06)
  * Microprice Ponderado L2 & Order Book Imbalance (PolyResearch Robotics)
  * Teto de Preço Sniper: $0.55 (PRIMARY_MAX_PRICE) e Piso $0.35 (PRIMARY_MIN_PRICE)
  * Verificação de Liquidez Real: Profundidade mínima no Best Ask da CLOB
  * Filtro Jev Trend Continuation (Alinhamento com vela de 5m anterior da Binance)
  * Bússola Macro BTC (Jev Lead-Lag Architecture contra Fakeouts)
  * Take-Profit Antecipado (SirMartingale): Venda com lucro se Best Bid bater >= 86¢
  * Stop-Loss de Emergência (Bonereaper): Liquidação antecipada se delta reverter
- Modo: PAPER HYPER-REALISTA (Consome livro L2 real, valida liquidez e simula preenchimento taker)
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
    validate_clob_spread_gate,
    check_sol_cross_asset_beta_lag_gate,
    check_dow_counter_trend_veto,
    record_desk_trade_result,
    check_kalshi_synpath_fomo_gate
)
from execution_math import (
    calculate_vwap_ask,
    calculate_vwap_bid,
    calculate_executable_edge,
    compute_fractional_kelly_stake,
    bayesian_fair_value
)
from anti_sweep_shield import evaluate_anti_sweep_shield
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
    OrderArgsV2,
    OrderType,
    BalanceAllowanceParams,
    AssetType
)
from py_clob_client_v2.order_builder.builder import ROUNDING_CONFIG

for _ts in ROUNDING_CONFIG:
    ROUNDING_CONFIG[_ts].amount = min(4, ROUNDING_CONFIG[_ts].amount)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
LIVE_STATE_JSON = os.path.join(BASE_DIR, "sol_live_market_state.json")

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
SOL_MODE = ENV_CFG.get("SOL_MODE", "PAPER").upper()
JOURNAL_JSON = os.path.join(BASE_DIR, "sol_trading_journal.json" if SOL_MODE == "LIVE" else "sol_paper_journal.json")

# ===================== PARÂMETROS QUANTITATIVOS (JEV AI CALIBRATED) =====================
FIXED_STAKE = 1.00                # $1.00 por aposta (Trava Estrita Micro-Institucional JEV / Benchmark Desk 1 & 3B)
DEADBAND_BPS = 0.00080            # 8.0 bps (0.080%) do preço da SOL
DEADBAND_MIN_FLOOR = 0.10         # Piso mínimo de $0.10 de variação na SOL (Blindagem contra micro-ruído)
PRIMARY_MAX_PRICE = 0.55          # Preço máximo de entrada (55¢ - Alinhado estritamente com Desk 1 para EV positivo)
PRIMARY_MIN_PRICE = 0.40          # Preço mínimo de entrada (40¢ - elimina cotas de cauda com spread tóxico)
MAX_CLOB_SPREAD = 0.05            # Spread máximo aceito no book (5¢ - alinhado à liquidez institucional)
MAX_ORACLE_STRIKE_DISCREPANCY_USD = 0.35 # Teto máximo de discrepância Binance vs Chainlink na abertura (~30 bps / JEV Shield)
TAKE_PROFIT_PRICE = 0.86          # Take Profit antecipado (86¢)
STOP_LOSS_MIN_BID = 0.15          # Bid mínimo aceito para Stop Loss na CLOB
REVERSAL_MULTIPLIER = 1.8         # Multiplicador do deadband para confirmar reversão real (evita ruído de repique)
STOP_LOSS_MIN_TIME_SEC = 200      # Tempo mínimo decorrido (200s / 3m20s) para avaliar stop-loss
EVAL_POINT_SEC = 135              # 135s (2m15s da vela de 5m / 45% da vela - Sweet-Spot Institucional Desk 1)
REQUIRE_PRIOR_CANDLE = True       # Filtro Jev Trend Continuation
CHAINLINK_SOL_AGGREGATOR = "0x10C8264C0935b3B9870013e057f330Ff3e9C56dC" # Oráculo Oficial Chainlink SOL/USD Polygon Mainnet (8 dec)

# ===================== DATA PROVIDERS (CHAINLINK ON-CHAIN + BINANCE REF) =====================
def get_chainlink_sol_price() -> Optional[float]:
    """
    Consulta a cotação oficial do Oráculo Chainlink SOL/USD (8 decimais)
    diretamente no contrato AggregatorV3 da Polygon (0x10C8264C0935b3B9870013e057f330Ff3e9C56dC)
    usando eth_call (latestRoundData selector 0xfeaf968c). Sub-segundo via RPC Polygon/Alchemy.
    """
    cfg = load_env_config()
    custom_rpc = cfg.get("POLYGON_RPC_URL") or cfg.get("RPC_URL")
    rpcs = [
        "https://polygon-mainnet.g.alchemy.com/v2/alch_SpigbpkWNlbSTj_AbkO4I",
        "https://polygon-bor.publicnode.com",
        "https://polygon.drpc.org",
        "https://gateway.tenderly.co/public/polygon",
        "https://polygon.publicnode.com"
    ]
    if custom_rpc and custom_rpc not in rpcs:
        rpcs.insert(0, custom_rpc)

    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_call",
        "params": [
            {"to": CHAINLINK_SOL_AGGREGATOR, "data": "0xfeaf968c"},
            "latest"
        ],
        "id": 1
    }).encode("utf-8")

    for rpc in rpcs:
        try:
            req = urllib.request.Request(
                rpc,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=2.5) as r:
                res = json.loads(r.read().decode("utf-8"))
                if "result" in res and res["result"] and len(res["result"]) >= 130:
                    ans_hex = res["result"][66:130]
                    price = int(ans_hex, 16) / 1e8
                    if price > 10.0:
                        return round(price, 4)
        except Exception:
            continue
    return None

def get_binance_sol_spot() -> Optional[float]:
    """Preço Spot em tempo real da Solana (SOL/USDT) na Binance (Referência e Fallback)"""
    urls = [
        "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT",
        "https://data-api.binance.vision/api/v3/ticker/price?symbol=SOLUSDT"
    ]
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                return float(json.loads(r.read().decode())["price"])
        except Exception:
            pass
    return None

def get_binance_sol_5m_prior_candle() -> Optional[Dict[str, Any]]:
    """Consulta a última vela de 5m FECHADA na Binance para validação de tendência"""
    urls = [
        "https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=5m&limit=2",
        "https://data-api.binance.vision/api/v3/klines?symbol=SOLUSDT&interval=5m&limit=2"
    ]
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                data = json.loads(r.read().decode())
                if len(data) >= 2:
                    prior = data[0]
                    p_open = float(prior[1])
                    p_close = float(prior[4])
                    p_dir = "UP" if p_close >= p_open else "DOWN"
                    ret_bps = (abs(p_close - p_open) / p_open) * 10000
                    return {"dir": p_dir, "open": p_open, "close": p_close, "ret_bps": ret_bps}
        except Exception:
            pass
    return None

def get_sol_candle_open(window_ts: int) -> Optional[float]:
    """Fallback: Obtém a abertura da vela de 5m correspondente ao window_ts na Binance"""
    url = f"https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=5m&startTime={window_ts * 1000}&limit=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode())
            if data and len(data) > 0:
                return float(data[0][1])
    except Exception:
        pass
    return None

def get_binance_btc_spot() -> Optional[float]:
    """Preço Spot em tempo real do Bitcoin (BTC/USDT) na Binance (Bússola Macro)"""
    urls = [
        "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
        "https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT"
    ]
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                return float(json.loads(r.read().decode())["price"])
        except Exception:
            pass
    return None

def get_btc_candle_open(window_ts: int) -> Optional[float]:
    """Abertura da vela de 5m de BTC correspondente ao window_ts (Bússola Macro)"""
    url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&startTime={window_ts * 1000}&limit=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode())
            if data and len(data) > 0:
                return float(data[0][1])
    except Exception:
        pass
    return None

# ===================== POLYMARKET CLOB & GAMMA API =====================
def get_polymarket_sol_market(window_ts: int) -> Optional[Dict[str, Any]]:
    """Busca o mercado oficial de Solana 5m na Gamma API da Polymarket"""
    slug = f"sol-updown-5m-{window_ts}"
    url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PolymarketSolPaperBot/2.0"})
        with urllib.request.urlopen(req, timeout=3.5) as r:
            data = json.loads(r.read().decode())
            if data and len(data) > 0:
                return data[0]
    except Exception:
        pass
    return None

def get_clob_orderbook(token_id: str) -> Optional[Dict[str, Any]]:
    """
    Consulta o Order Book L2 oficial diretamente da CLOB da Polymarket
    e extrai métricas de microestrutura e profundidade real (filtra ordens < 1 cota):
    - best_bid, best_ask
    - spread
    - top_imbalance (L1) e depth_imbalance (profundidade total)
    - microprice (Stoikov volume-weighted fair price)
    - top_bid_size, top_ask_size (liquidez disponível imediatamente)
    """
    url = f"https://clob.polymarket.com/book?token_id={token_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PolymarketSolPaperBot/2.0"})
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

# ===================== SOLANA ALGO TRADER ENGINE (LIVE + PAPER) =====================
class SolanaTrader5M:
    def __init__(self):
        self.mode = SOL_MODE
        self.balance = 20.7094 # Saldo real inicial / compartilhado Safe
        self.trades = []
        self.current_open_position = None
        self.traded_windows = set()
        self.candle_strikes = {}
        self.binance_opens = {}
        self.client: Optional[ClobClient] = None

        self.load_journal()

        if self.mode == "LIVE":
            print(f"-> [MODO REAL ATIVO]: Conectando ao Polymarket CLOB V2...")
            if not POLYGON_PRIVATE_KEY:
                print("[ERRO FATAL] POLYGON_PRIVATE_KEY não configurada no .env!")
                sys.exit(1)
            try:
                self.client = ClobClient(
                    host="https://clob.polymarket.com",
                    key=POLYGON_PRIVATE_KEY,
                    chain_id=137,
                    signature_type=SignatureTypeV2.POLY_1271,
                    funder=POLY_FUNDER_ADDRESS
                )
                creds = self.client.derive_api_key()
                self.client.set_api_creds(creds)
                print("   -> Conexão L1/L2 com Polymarket CLOB V2 estabelecida para Desk 2 (SOL)!")
                real_bal = self.get_usdc_balance()
                print(f"   -> Saldo Real em Carteira Polygon (USDC): ${real_bal:,.2f} USDC")
            except Exception as e:
                print(f"[ERRO ao autenticar ClobClient Solana]: {e}")
                self.client = None
        else:
            print("-> [MODO PAPER ATIVO]: Operando com simulação no Order Book L2 real.")

    def get_usdc_balance(self) -> float:
        """Consulta o saldo real de USDC na conta Polymarket via CLOB V2.
        Em caso de falha de rede/timeout, retorna o saldo em cache (self.balance)
        em vez de -1.0, evitando que a trava de segurança ($15) seja acionada
        falsamente por instabilidade de API."""
        if self.mode == "PAPER":
            return self.balance
        if not self.client:
            return 0.0
        try:
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            info = self.client.get_balance_allowance(params)
            raw_bal = float(info.get("balance", 0.0))
            bal = raw_bal / 1e6
            self.balance = round(bal, 4)
            return self.balance
        except Exception as e:
            # CORRECAO JEV: Retorna saldo em cache para evitar trava falsa.
            # -1.0 causaria -1.0 < 15.00 = True → bot paralisado silenciosamente.
            cached = self.balance if self.balance > 0 else 0.0
            print(f"[AVISO API SALDO SOL]: Falha ao consultar CLOB ({e}). Usando saldo em cache: ${cached:.4f} USDC.")
            return cached

    def get_token_balance(self, token_id: str) -> float:
        """Consulta o saldo real de cotas de um token condicional na carteira Safe"""
        if self.mode == "PAPER":
            return 0.0
        if not self.client or not token_id:
            return 0.0
        try:
            params = BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
            info = self.client.get_balance_allowance(params)
            raw_bal = float(info.get("balance", 0.0))
            return raw_bal / 1e6
        except Exception:
            return 0.0

    def get_latest_clob_fill(self, token_id: str, side: str = "SELL", min_timestamp: Optional[int] = None) -> Optional[dict]:
        """Obtém o fill mais recente na CLOB filtrado estritamente por token, lado e timestamp"""
        if not self.client or not token_id:
            return None
        try:
            trades = self.client.get_trades()
            if not trades:
                return None
            sorted_trades = sorted(trades, key=lambda x: int(x.get("match_time", 0)), reverse=True)
            for tr in sorted_trades:
                if tr.get("side") != side:
                    continue
                if str(tr.get("asset_id", "")) != str(token_id):
                    continue
                m_time = int(tr.get("match_time", 0))
                if min_timestamp and m_time < (min_timestamp - 30):
                    continue
                return {
                    "price": float(tr.get("price", 0.0)),
                    "size": float(tr.get("size", 0.0)),
                    "tx_hash": tr.get("transaction_hash", ""),
                    "match_time": m_time
                }
        except Exception as e:
            print(f"[get_latest_clob_fill erro]: {e}")
        return None

    def place_live_order(self, token_id: str, side: str, amount: float, price: Optional[float] = None, post_only: bool = False) -> Dict[str, Any]:
        """Cria e envia ordem real para o Polymarket CLOB V2 (BUY em USDC ou cotas, SELL em cotas; suporta post_only Maker)"""
        halted, halt_msg = is_system_halted()
        if halted:
            print(f"🛑 [RISK GATE VETO]: Tentativa de ordem bloqueada ({halt_msg})")
            return {"status": "ERROR", "error": f"VETO_KILL_SWITCH: {halt_msg}"}

        if self.mode == "PAPER":
            mock_id = f"paper-{int(time.time()*1000)}"
            mock_tx = f"0xpaper{int(time.time()*1000):016x}"
            return {
                "status": "SUCCESS",
                "response": {
                    "orderID": mock_id,
                    "transactionsHashes": [mock_tx],
                    "paper": True
                }
            }

        if not self.client:
            return {"status": "ERROR", "error": "ClobClient desconectado"}

        order_price = price if price is not None else 0

        try:
            if post_only and order_price > 0:
                # Maker Inteligente (JEV Touch Quoting): Ordem limite Post-Only GTC que descansa no livro
                calc_size = round(amount / order_price, 2) if side == "BUY" else round(amount, 2)
                order_args = OrderArgsV2(
                    token_id=token_id,
                    price=order_price,
                    size=calc_size,
                    side=side
                )
                signed_order = self.client.create_order(order_args)
                resp = self.client.post_order(signed_order, order_type=OrderType.GTC, post_only=True)
                return {"status": "SUCCESS", "response": resp, "maker_post_only": True}
            else:
                market_args = MarketOrderArgsV2(
                    token_id=token_id,
                    amount=amount,
                    side=side,
                    price=order_price,
                    order_type=OrderType.FAK
                )
                signed_order = self.client.create_market_order(market_args)
                resp = self.client.post_order(signed_order, order_type=OrderType.FAK)
                return {"status": "SUCCESS", "response": resp}
        except Exception as e:
            err_str = str(e)
            # Reconciliação Anti-Trade Fantasma:
            # Em caso de timeout de rede (ex: 'The read operation timed out'), a API pode ter executado a ordem.
            if side == "BUY":
                try:
                    time.sleep(1.5)
                    tok_bal = self.get_token_balance(token_id)
                    if tok_bal and tok_bal >= 0.5:
                        print(f"       [🚨 RECUPERAÇÃO ANTI-FANTASMA]: Timeout de rede ocorreu, mas {tok_bal:.4f} cotas foram confirmadas na Safe!")
                        return {
                            "status": "SUCCESS",
                            "response": {
                                "orderID": "RECONCILED_ONCHAIN",
                                "transactionsHashes": [],
                                "reconciled": True
                            }
                        }
                except Exception:
                    pass
            elif side == "SELL":
                try:
                    time.sleep(1.5)
                    tok_bal = self.get_token_balance(token_id)
                    if tok_bal is not None and tok_bal < 0.1:
                        print(f"       [🚨 RECUPERAÇÃO ANTI-FANTASMA]: Timeout na venda, mas cotas foram zeradas na Safe (venda confirmada)!")
                        return {
                            "status": "SUCCESS",
                            "response": {
                                "orderID": "RECONCILED_ONCHAIN",
                                "transactionsHashes": [],
                                "reconciled": True
                            }
                        }
                except Exception:
                    pass
            return {"status": "FAILED", "error": err_str}

    def load_journal(self):
        if os.path.exists(JOURNAL_JSON):
            try:
                with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if self.mode == "PAPER":
                        self.balance = float(data.get("current_balance", self.balance))
                    self.trades = data.get("trades", [])
                    self.traded_windows = {int(t.get("window_ts") or t.get("cycle_ts", 0)) for t in self.trades if ("window_ts" in t or "cycle_ts" in t)}
            except Exception:
                pass

    def save_journal(self, trade_data: dict):
        self.trades.append(trade_data)
        wins = sum(1 for t in self.trades if "VITÓRIA" in t.get("result", ""))
        losses = sum(1 for t in self.trades if "DERROTA" in t.get("result", ""))
        total = len(self.trades)
        wr = round(wins / total * 100, 1) if total > 0 else 0.0

        journal = {
            "mode": f"{self.mode}_SOL_5M_CLOB_REAL",
            "current_balance": round(self.balance, 4),
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": wr,
            "funder_verified": POLY_FUNDER_ADDRESS,
            "trades": self.trades
        }
        atomic_write_json(JOURNAL_JSON, journal)
        try:
            is_win = ("VITÓRIA" in str(trade_data.get("result", "")).upper()) or (float(trade_data.get("pnl", 0.0)) >= 0)
            record_desk_trade_result("desk2", is_win=is_win, pnl=float(trade_data.get("pnl", 0.0)))
        except Exception:
            pass

    def save_live_state(self, state: dict):
        atomic_write_json(LIVE_STATE_JSON, state)

    def run_cycle(self):
        now_ts = int(time.time())
        window_ts = (now_ts // 300) * 300
        elapsed_sec = now_ts - window_ts
        remaining_sec = max(0, 300 - elapsed_sec)
        dt_str = datetime.fromtimestamp(window_ts, timezone.utc).strftime("%d/%m/%Y %H:%M:%S")
        time_only_str = datetime.fromtimestamp(window_ts, timezone.utc).strftime("%H:%M:%S")

        # Verificacao de Kill-Switch Global via Arquivo ('HALT' ou 'EMERGENCY_STOP')
        halt_file = os.path.join(BASE_DIR, "HALT")
        emergency_file = os.path.join(BASE_DIR, "EMERGENCY_STOP")
        if os.path.exists(halt_file) or os.path.exists(emergency_file):
            print(f"\n    [🚨 KILL-SWITCH GLOBAL ATIVADO]: Arquivo de emergencia detectado. Nenhuma ordem sera aberta.")
            time.sleep(10)
            return

        if window_ts in self.traded_windows:
            time.sleep(5)
            return

        print("\n" + "=" * 90)
        print(f"  ⚡ [SOLANA 5M {self.mode} - POLYMARKET CLOB V2]")
        print(f"  Janela Ativa: {dt_str} UTC | Timestamp: {window_ts} | Restam: {remaining_sec}s")
        print(f"  Funder Verificado: {POLY_FUNDER_ADDRESS[:10]}... | Saldo {self.mode}: ${self.balance:,.2f} USD")
        print("=" * 90)

        # Checagem do Variable Bench e Disjuntores (Universal 2-Loss + Coin-Flip - JEV AI)
        journal_path = JOURNAL_JSON
        is_benched, bench_reason, bench_rem = bench.check_consecutive_losses_breaker("desk2", journal_path, max_consecutive_losses=2, cooldown_seconds=1800)
        if not is_benched:
            is_benched, bench_reason, bench_rem = bench.check_coin_flip_breaker("desk2", journal_path)
        if not is_benched:
            is_benched, bench_reason, bench_rem = bench.is_benched("desk2")
        if is_benched:
            print(f"\n   [🛑 VARIABLE BENCH]: Desk 2 em cooldown ({bench_reason}) — restam {bench_rem:.1f}s. Aguardando...")
            time.sleep(min(15, max(2, int(bench_rem))))
            return

        # Se em modo LIVE, valida saldo e piso de proteção antes de prosseguir
        if self.mode == "LIVE":
            live_bal = self.get_usdc_balance()
            # Guarda extra: saldo zero ou negativo indica falha total de API sem cache válido
            if live_bal <= 0:
                print(f"   [AVISO SALDO]: API retornou ${live_bal:.2f} sem cache valido. Pulando ciclo por cautela.")
                time.sleep(10)
                return
            if live_bal < 15.00:
                print(f"   [TRAVA DE SEGURANCA]: Saldo Safe (${live_bal:.2f} USDC) abaixo do piso de protecao ($15.00). Preservando deposito.")
                time.sleep(10)
                return
            if live_bal < FIXED_STAKE:
                print(f"   [!] Saldo insuficiente para aposta ({live_bal:.2f} < ${FIXED_STAKE:.2f} USDC). Aguardando fundos...")
                time.sleep(10)
                return

        # 1. Busca Mercado Oficial na Gamma API da Polymarket
        market = get_polymarket_sol_market(window_ts)
        token_up = None
        token_down = None
        market_slug = f"sol-updown-5m-{window_ts}"
        market_title = f"Solana Up or Down 5m ({dt_str} UTC)"

        if market:
            try:
                tokens = json.loads(market.get("clobTokenIds", "[]"))
                if len(tokens) >= 2:
                    token_up = tokens[0]
                    token_down = tokens[1]
                market_title = market.get("question", market_title)
            except Exception:
                pass

        # 2. Busca Strike Price Oficial (Oraculo Chainlink) e Abertura Binance
        if window_ts in self.candle_strikes:
            strike = self.candle_strikes[window_ts]
        else:
            strike = get_chainlink_sol_price()
            if not strike or strike <= 0:
                strike = get_sol_candle_open(window_ts) or get_binance_sol_spot()
            if not strike or strike <= 0:
                print(f"    [🚨 FALHA CRÍTICA DE ORÁCULO]: Impossível capturar Strike aos :00. Abortando janela {window_ts}.")
                self.traded_windows.add(window_ts)
                return
            self.candle_strikes[window_ts] = strike

        if window_ts in self.binance_opens:
            binance_open = self.binance_opens[window_ts]
        else:
            binance_open = get_sol_candle_open(window_ts) or get_binance_sol_spot() or strike
            if binance_open:
                self.binance_opens[window_ts] = binance_open

        # Discrepancy Shield (Binance vs Chainlink)
        feed_diff = abs(binance_open - strike)
        print(f"    Strike Oraculo Chainlink (K): ${strike:.4f} | Binance Ref: ${binance_open:.4f} (Spread: ${feed_diff:+.4f})")
        if feed_diff > MAX_ORACLE_STRIKE_DISCREPANCY_USD:
            print(f"    [🛡️ VETO DISCREPÂNCIA DE ORÁCULO]: Feed Binance (${binance_open:.4f}) diverge do Chainlink (${strike:.4f}) por ${feed_diff:.4f} (> ${MAX_ORACLE_STRIKE_DISCREPANCY_USD:.2f}). Abortando janela para proteger capital.")
            self.traded_windows.add(window_ts)
            return

        evaluated_entry = False

        # Loop de monitoramento contínuo da vela (a cada 2 segundos)
        while True:
            cur_time = time.time()
            cur_elapsed = int(cur_time - window_ts)
            cur_left = max(0, 300 - cur_elapsed)

            if cur_elapsed >= 298:
                break

            # Consulta Spot via Oráculo Chainlink Oficial (com Fallback Binance)
            spot_now = get_chainlink_sol_price() or get_binance_sol_spot()
            if not spot_now:
                time.sleep(2)
                continue

            delta = spot_now - strike
            dynamic_deadband, sol_regime = get_dynamic_deadband_gate(strike, base_bps=DEADBAND_BPS, min_floor=DEADBAND_MIN_FLOOR, symbol="SOLUSDT")

            # Consulta livros de ordens reais na CLOB da Polymarket
            book_up = get_clob_orderbook(token_up) if token_up else None
            book_down = get_clob_orderbook(token_down) if token_down else None

            # Determina lado candidato
            candidate_side = None
            target_token = None
            target_book = None

            if delta >= dynamic_deadband:
                candidate_side = "UP"
                target_token = token_up
                target_book = book_up
            elif delta <= -dynamic_deadband:
                candidate_side = "DOWN"
                target_token = token_down
                target_book = book_down

            # Status signal description
            if cur_elapsed < EVAL_POINT_SEC:
                status_sig = f"Monitorando CLOB Polymarket (Restam {EVAL_POINT_SEC - cur_elapsed}s para decisão)"
            else:
                if abs(delta) < dynamic_deadband:
                    status_sig = f"Deadband Ativo: Delta (${delta:+.3f}) no ruído (< ${dynamic_deadband:.3f} | Regime: {sol_regime.get('regime')} {sol_regime.get('deadband_multiplier')}x)"
                else:
                    status_sig = f"Sinal Intra-Vela: {candidate_side} | Delta: ${delta:+.3f} (Deadband: ${dynamic_deadband:.3f})"

            # Publica estado em tempo real para o dashboard
            state_payload = {
                "timestamp": cur_time,
                "window_ts": window_ts,
                "market_slug": market_slug,
                "market_title": market_title,
                "token_up": token_up,
                "token_down": token_down,
                "spot": spot_now,
                "strike": strike,
                "delta": delta,
                "deadband": dynamic_deadband,
                "diurnal_regime": sol_regime.get("regime", "NEUTRAL"),
                "deadband_mult": sol_regime.get("deadband_multiplier", 1.0),
                "seconds_elapsed": cur_elapsed,
                "seconds_left": cur_left,
                "progress_pct": min(100.0, round((cur_elapsed / 300.0) * 100.0, 1)),
                "status_signal": status_sig,
                "funder_verified": POLY_FUNDER_ADDRESS,
                "mode": self.mode,
                "is_live": (self.mode == "LIVE"),
                "paper_balance": round(self.balance, 4),
                "live_balance": round(self.balance, 4),
                "open_position": self.current_open_position,
                "clob_up": book_up,
                "clob_down": book_down
            }
            self.save_live_state(state_payload)

            # -------------------------------------------------------------
            # 2. PONTO QUANTITATIVO DE ENTRADA ({EVAL_POINT_SEC}s)
            # -------------------------------------------------------------
            if cur_elapsed >= EVAL_POINT_SEC and not evaluated_entry and self.current_open_position is None:
                evaluated_entry = True
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🎯 PONTO DE DECISÃO QUANTITATIVA ({EVAL_POINT_SEC}s):")
                print(f"   Strike: ${strike:.2f} | Spot Atual: ${spot_now:.2f} | Delta: ${delta:+.4f}")
                print(f"   Deadband Dinâmico: ${dynamic_deadband:.4f} ({DEADBAND_BPS*10000:.1f} bps)")

                if not candidate_side:
                    print(f"   -> [🛡️ FILTRO DEADBAND]: Delta (${delta:+.4f}) na zona morta (< ${dynamic_deadband:.4f}). Preservando capital.")
                else:
                    if not target_book:
                        # Fallback de Gamma API se o orderbook CLOB estiver unilateral ou sem book bilateral
                        gamma_p = None
                        if market:
                            try:
                                out_prices = json.loads(market.get("outcomePrices", "[]")) if isinstance(market.get("outcomePrices"), str) else market.get("outcomePrices", [])
                                t_idx = 0 if candidate_side == "UP" else 1
                                if len(out_prices) > t_idx:
                                    gamma_p = float(out_prices[t_idx])
                            except Exception:
                                pass
                        if gamma_p and PRIMARY_MIN_PRICE <= gamma_p <= PRIMARY_MAX_PRICE:
                            target_book = {
                                "best_bid": round(gamma_p - 0.02, 4),
                                "best_ask": round(gamma_p, 4),
                                "spread": 0.02,
                                "mid_price": round(gamma_p - 0.01, 4),
                                "top_bid_size": 50.0,
                                "top_ask_size": 50.0,
                                "sum_bid_size": 50.0,
                                "sum_ask_size": 50.0,
                                "top_imbalance": 0.0,
                                "depth_imbalance": 0.0,
                                "microprice": round(gamma_p, 4),
                                "bids_raw": [(round(gamma_p - 0.02, 2), 50.0)],
                                "asks_raw": [(round(gamma_p, 2), 50.0)],
                                "fallback_gamma": True
                            }
                            print(f"   -> [ℹ️ FALLBACK GAMMA API]: Book CLOB unilateral; utilizando cotacao oficial Gamma (${gamma_p:.3f}).")
                        else:
                            print(f"   -> [🛡️ FILTRO LIVRO]: Book CLOB indisponivel e Gamma (${gamma_p}) fora da faixa. Preservando capital.")

                if candidate_side and target_book:
                    # Filtro JEV Trend Continuation
                    prior_candle = get_binance_sol_5m_prior_candle()
                    prior_dir = prior_candle["dir"] if prior_candle else candidate_side
                    prior_ret = prior_candle["ret_bps"] if prior_candle else 0.0

                    if REQUIRE_PRIOR_CANDLE and prior_candle and prior_dir != candidate_side:
                        print(f"   -> [🛡️ VETO JEV]: Sinal {candidate_side} rejeitado por divergir da vela 5m anterior ({prior_dir} {prior_ret:.1f} bps).")
                    else:
                        # Bússola Macro BTC + Cross-Asset Beta Lag (CacheCarti Alpha)
                        btc_spot = get_binance_btc_spot()
                        btc_open = get_btc_candle_open(window_ts)
                        btc_veto = False
                        if btc_spot and btc_open and strike and spot_now:
                            btc_delta = btc_spot - btc_open
                            btc_ret_pct = btc_delta / btc_open
                            btc_drift_bps = btc_ret_pct * 10000.0
                            sol_ret_pct = delta / strike

                            beta_ok, beta_msg, beta_info = check_sol_cross_asset_beta_lag_gate(
                                target_side=candidate_side,
                                sol_delta_pct=sol_ret_pct,
                                btc_delta_pct=btc_ret_pct
                            )
                            if not beta_ok:
                                btc_veto = True
                                print(f"   -> [🛡️ VETO CROSS-ASSET BETA (CacheCarti Alpha)]: {beta_msg}")
                            elif beta_info.get("is_sol_lagging") and beta_info.get("is_btc_impulse"):
                                print(f"   -> [🔥 BOOST CROSS-ASSET CATCH-UP]: {beta_msg}")
                            elif candidate_side == "UP" and btc_drift_bps < -15.0:
                                btc_veto = True
                                print(f"   -> [🛡️ VETO MACRO BTC]: Sinal UP rejeitado! BTC em queda pronunciada ({btc_drift_bps:+.1f} bps / Delta: ${btc_delta:+.1f}).")
                            elif candidate_side == "DOWN" and btc_drift_bps > 15.0:
                                btc_veto = True
                                print(f"   -> [🛡️ VETO MACRO BTC]: Sinal DOWN rejeitado! BTC em alta pronunciada ({btc_drift_bps:+.1f} bps / Delta: ${btc_delta:+.1f}).")

                        # REGRA DE PROTEÇÃO CONTRA CONTRATENDÊNCIA DOW REGIME (Charles Dow & Raghee Horner / JEV AI)
                        if not btc_veto:
                            dow_ok, dow_msg, dow_info = check_dow_counter_trend_veto(
                                target_side=candidate_side,
                                symbol="SOLUSDT",
                                min_slope_bps=10.0,
                                deadband_delta=delta,
                                strong_reversal_threshold=2.0 * dynamic_deadband
                            )
                            if not dow_ok:
                                btc_veto = True
                                print(f"   -> [🛡️ VETO DOW REGIME SOL - JEV]: {dow_msg}")
                            else:
                                print(f"   -> [📈 DOW REGIME SHIELD SOL]: {dow_msg}")

                        if not btc_veto:
                            # Verificação de Microestrutura e Liquidez Real na CLOB
                            best_ask = target_book["best_ask"]
                            best_bid = target_book["best_bid"]
                            spread = target_book["spread"]
                            ask_size = target_book["top_ask_size"]
                            microprice = target_book["microprice"]

                            print(f"\n   [⚡ LIVRO CLOB POLYMARKET REAL ({candidate_side})]:")
                            print(f"      Best Bid: ${best_bid:.2f} | Best Ask: ${best_ask:.2f} | Spread: ${spread:.4f}")
                            print(f"      Microprice: ${microprice:.4f} | Tamanho Topo Ask: {ask_size:.1f} cotas")

                            # Filtros de Execução Realista (Wiley 2025 / Aval JEV 90%)
                            spread_ok, spread_msg, spread_info = validate_clob_spread_gate(
                                spread=spread,
                                best_bid=best_bid,
                                best_ask=best_ask,
                                top_ask_size=ask_size,
                                target_stake_usd=FIXED_STAKE,
                                max_tolerable_spread=0.050,
                                optimal_spread_ceiling=0.035,
                                delay_tolerable_spread=0.065
                            )
                            if not spread_ok:
                                print(f"   -> [🛡️ FILTRO SPREAD CLOB]: {spread_msg}. Abortando entrada por liquidez tóxica.")
                            elif best_ask > PRIMARY_MAX_PRICE:
                                print(f"   -> [🛡️ FILTRO TETO DE PREÇO]: Best Ask ${best_ask:.2f} > ${PRIMARY_MAX_PRICE:.2f}. EV desfavorável.")
                            elif best_ask < PRIMARY_MIN_PRICE:
                                print(f"   -> [🛡️ FILTRO PISO DE PREÇO]: Best Ask ${best_ask:.2f} < ${PRIMARY_MIN_PRICE:.2f}. Risco de reversão assimétrica.")
                            else:
                                # Pricing Black-Scholes + Bayesiano para SOL
                                sec_left = max(1, 300 - int(cur_time - window_ts))
                                eff_vol = 0.55  # Volatilidade intra-vela de SOL (~55%)
                                tau = max(1.0, float(sec_left)) / (365.25 * 24 * 3600)
                                sig_sqrt_tau = eff_vol * math.sqrt(tau)
                                d2 = (math.log(max(1.0, spot_now) / max(1.0, strike)) - 0.5 * (eff_vol ** 2) * tau) / max(1e-9, sig_sqrt_tau)
                                bs_prob_up = 0.5 * (1.0 + math.erf(d2 / math.sqrt(2.0)))
                                bs_fair = bs_prob_up if candidate_side == "UP" else (1.0 - bs_prob_up)

                                p_sig = 0.65 if target_book.get("top_imbalance", 0) > 0.1 else (0.35 if target_book.get("top_imbalance", 0) < -0.1 else 0.50)
                                model_fair_value = bayesian_fair_value(
                                    prior_prob=bs_fair,
                                    p_signal_if_outcome=p_sig if candidate_side == "UP" else (1.0 - p_sig),
                                    p_signal_if_alternative=0.50,
                                    collinearity_discount=0.75
                                )

                                # Dimensionamento Estrito Micro-Institucional JEV (Benchmark Desk 3B)
                                real_bal = self.get_usdc_balance() if self.mode == "LIVE" else self.balance
                                btc_reserve = 3.00 if self.mode == "LIVE" else 0.00
                                cur_bankroll = max(10.0, real_bal - btc_reserve)
                                # Em LIVE, travar estritamente no FIXED_STAKE ($1.00) eliminando Kelly elástico agressivo
                                min_stake_val = FIXED_STAKE
                                max_stake_val = FIXED_STAKE if self.mode == "LIVE" else min(2.50, max(1.00, round(cur_bankroll * 0.08, 2)))
                                target_stake, kelly_status = compute_dynamic_stake(
                                    bankroll=cur_bankroll,
                                    win_probability=model_fair_value,
                                    entry_price=best_ask,
                                    fallback_stake=FIXED_STAKE,
                                    kelly_fraction=0.25,
                                    min_stake=min_stake_val,
                                    max_stake=max_stake_val
                                )
                                if self.mode == "LIVE" and target_stake > FIXED_STAKE:
                                    target_stake = FIXED_STAKE

                                if target_stake <= 0.0:
                                    print(f"   -> [🛡️ VETO KELLY FRACIONÁRIO]: {kelly_status}. Edge insuficiente.")
                                    continue

                                # VWAP na profundidade real do livro
                                asks_raw = target_book.get("asks_raw", [])
                                vwap_price, vwap_cost, vwap_shares, slip_bps = calculate_vwap_ask(asks_raw, target_usd=target_stake)

                                if vwap_price is None:
                                    print(f"   -> [🛡️ FILTRO DE PROFUNDIDADE VWAP]: Livro raso! Profundidade (${vwap_cost:.2f}) insuficiente para ${target_stake:.2f}.")
                                    continue

                                # Validação Centralizada no RiskGate
                                gate_ok, gate_msg = check_pre_trade_gate(
                                    desk_id="DESK2_SOL_5M",
                                    target_side=candidate_side,
                                    stake=target_stake,
                                    spot_price=spot_now,
                                    strike_price=strike,
                                    oracle_timestamp=time.time(),
                                    current_balance=cur_bankroll,
                                    execution_mode=self.mode,
                                    fair_value=model_fair_value,
                                    vwap_price=vwap_price,
                                    min_net_edge=0.015
                                )
                                if not gate_ok:
                                    print(f"   -> [🛡️ RISK GATE VETO]: {gate_msg}")
                                    continue

                                print(f"   💎 [EXECUÇÃO APROVADA - VWAP + KELLY]:")
                                print(f"      Fair Value: {model_fair_value:.2%} | VWAP Fill: ${vwap_price:.4f} (Slippage: {slip_bps:.1f} bps)")
                                print(f"      Stake Kelly (25%): ${target_stake:.2f} ({kelly_status}) | Cotas: {vwap_shares:.2f}")

                                exec_price = vwap_price

                                # ── CÃO DE GUARDA JEV (Blindagem Anti-Exaustão e Anti-Repique SOL 5M) ──
                                try:
                                    from jev_microstructure_gate import jev_gate
                                    delta_val = spot_now - strike
                                    clob_sp = target_book.get("spread", 0.03)
                                    obi_val = target_book.get("top_imbalance", 0.0)
                                    jev_res = jev_gate.evaluate_entry(
                                        desk_id="desk2",
                                        delta_usd=delta_val,
                                        binance_drift=round(delta_val * 0.25, 2),
                                        clob_spread=clob_sp,
                                        contract_price=exec_price,
                                        oracle_discrepancy=0.10,
                                        seconds_left=int(sec_left),
                                        obi=obi_val,
                                        cvd=0.0,
                                        deadband_threshold=deadband_val if 'deadband_val' in locals() else 0.10,
                                        side=candidate_side,
                                        symbol="SOL"
                                    )
                                    if jev_res.get("verdict") == "VETO":
                                        print(f"   [🛑 VETO CÃO DE GUARDA JEV SOL]: {jev_res.get('veto_reason')} | Regime: {jev_res.get('candle_regime')}. Veto preventivo contra repique!")
                                        continue
                                except Exception as e:
                                    print(f"   [!] Aviso Jev Gate SOL: {e}")

                                # ── CROSS-VENUE SYNPATH FOMO TAKER FLOW GATE (SOL DUAL-VENUE INTELLIGENCE) ──
                                try:
                                    from zoneinfo import ZoneInfo
                                    end_s = ((int(time.time()) // 900) + 1) * 900
                                    end_u = datetime.fromtimestamp(end_s, tz=timezone.utc)
                                    end_ny = end_u.astimezone(ZoneInfo("America/New_York"))
                                    k_ticker = f"KXSOL15M-{end_ny.strftime('%y')}{end_ny.strftime('%b').upper()}{end_ny.strftime('%d')}{end_ny.strftime('%H')}{end_ny.strftime('%M')}-{end_ny.strftime('%M')}"
                                    k_side = "YES" if candidate_side == "UP" else "NO"

                                    fomo_ok, fomo_msg, fomo_data = check_kalshi_synpath_fomo_gate(
                                        ticker=k_ticker,
                                        target_side=k_side,
                                        threshold=0.70,
                                        min_volume=50.0,
                                        window_sec=60
                                    )
                                    if not fomo_ok:
                                        print(f"   [🛑 VETO CROSS-VENUE SYNPATH ANTI-FOMO SOL]: {fomo_msg}")
                                        print(f"      -> Kalshi {k_ticker}: Imbalance {fomo_data.get('imbalance', 0):+.2f} | Volume: {fomo_data.get('total_vol', 0):,.0f} contratos.")
                                        print(f"      -> Varejo comprando no topo de exaustão na Kalshi. Abortando entrada no Polymarket para proteger capital!")
                                        continue
                                    else:
                                        print(f"   [📊 CROSS-VENUE SYNPATH FLOW SOL]: {fomo_msg} (Kalshi {k_ticker})")
                                except Exception as e:
                                    print(f"   [Aviso Cross-Venue Synpath Gate SOL]: {e}")

                                if self.mode == "LIVE":
                                    print(f"\n   🚀 [ENVIANDO ORDEM REAL POLYMARKET CLOB V2 ({candidate_side})]:")
                                    print(f"      Token: {target_token[:14]}... | Preço VWAP: ${exec_price:.4f} | Stake: ${target_stake:.2f} USDC")

                                    maker_entry_attempted = False
                                    order_res = {}

                                    # Estratégia Maker Post-Only Inteligente (Touch Quoting JEV):
                                    # Se spread >= $0.02 e best_bid + 0.01 <= PRIMARY_MAX_PRICE: cota 1 tick dentro do touch
                                    if spread >= 0.02 and best_bid > 0 and (best_bid + 0.01) <= PRIMARY_MAX_PRICE:
                                        touch_price = round(best_bid + 0.01, 2)
                                        print(f"      [🎯 MAKER POST-ONLY JEV]: Cotando 1 tick dentro do spread a ${touch_price:.2f} (Best Bid: ${best_bid:.2f} | Best Ask: ${best_ask:.2f})...")
                                        post_res = self.place_live_order(target_token, "BUY", target_stake, price=touch_price, post_only=True)
                                        if post_res.get("status") == "SUCCESS":
                                            maker_order_id = post_res.get("response", {}).get("orderID", "")
                                            print(f"      -> Ordem Post-Only enviada com sucesso (ID: {maker_order_id})! Aguardando fill passivo...")
                                            maker_entry_attempted = True
                                            for _mk_chk in range(5):  # Monitora por até 10 segundos
                                                time.sleep(2.0)
                                                mk_bal = self.get_token_balance(target_token)
                                                if mk_bal and mk_bal >= 0.5:
                                                    order_res = post_res
                                                    exec_price = touch_price
                                                    print(f"      🎉 [MAKER FILL CONCLUÍDO]: Ordem preenchida passivamente a ${touch_price:.2f}! Spread capturado.")
                                                    break
                                            if not (order_res.get("status") == "SUCCESS"):
                                                print(f"      [⏳ MAKER TIMEOUT]: Ordem Post-Only não preenchida em 10s. Cancelando ordem resting...")
                                                try:
                                                    if maker_order_id:
                                                        self.client.cancel_order(maker_order_id)
                                                except Exception:
                                                    pass
                                                maker_entry_attempted = False

                                    if not maker_entry_attempted:
                                        order_res = self.place_live_order(target_token, "BUY", target_stake, price=exec_price, post_only=False)

                                    if order_res.get("status") == "SUCCESS":
                                        resp_data = order_res.get("response", {})
                                        order_id = resp_data.get("orderID") or "N/A"
                                        tx_hashes = resp_data.get("transactionsHashes") or []
                                        tx_hash = tx_hashes[0] if tx_hashes else order_id

                                        # Verificacao rigorosa de cotas reais recebidas na carteira Safe
                                        time.sleep(1.5)
                                        real_tok = self.get_token_balance(target_token)
                                        if real_tok is not None and real_tok >= 0.5:
                                            shares = round(real_tok, 4)
                                        else:
                                            print(f"      [AVISO FAK KILLED] Ordem enviada mas sem contraparte no book (saldo: {real_tok:.2f} cotas).")
                                            self.get_usdc_balance()
                                            continue

                                        self.get_usdc_balance()

                                        self.current_open_position = {
                                            "window_ts": window_ts,
                                            "time_str": dt_str,
                                            "market_slug": market_slug,
                                            "token_id": target_token,
                                            "direction": candidate_side,
                                            "strike": strike,
                                            "entry_price": exec_price,
                                            "shares": shares,
                                            "stake": target_stake,
                                            "entry_time": cur_time,
                                            "clob_spread": spread,
                                            "clob_best_bid": best_bid,
                                            "clob_best_ask": best_ask,
                                            "order_id": order_id,
                                            "tx_hash": tx_hash,
                                            "mode": "LIVE"
                                        }
                                        print(f"      -> ORDEM REAL EXECUTADA COM SUCESSO! ID: {order_id} | Tx: {tx_hash}")
                                        print(f"      -> Cotas confirmadas em carteira: {shares} | Saldo Restante: ${self.balance:,.2f} USDC")
                                    else:
                                        # Dupla verificação no loop principal contra falha/timeout
                                        time.sleep(1.0)
                                        rec_tok = self.get_token_balance(target_token)
                                        if rec_tok is not None and rec_tok >= 0.5:
                                            shares = round(rec_tok, 4)
                                            self.get_usdc_balance()
                                            self.current_open_position = {
                                                "window_ts": window_ts,
                                                "time_str": dt_str,
                                                "market_slug": market_slug,
                                                "token_id": target_token,
                                                "direction": candidate_side,
                                                "strike": strike,
                                                "entry_price": exec_price,
                                                "shares": shares,
                                                "stake": target_stake,
                                                "entry_time": cur_time,
                                                "clob_spread": spread,
                                                "clob_best_bid": best_bid,
                                                "clob_best_ask": best_ask,
                                                "order_id": "RECONCILED_ONCHAIN",
                                                "tx_hash": "RECONCILED_ONCHAIN",
                                                "mode": "LIVE"
                                            }
                                            print(f"      [🚨 RECUPERAÇÃO DE ENTRADA]: Resposta indicou erro ({order_res.get('error')}), mas {shares:.4f} cotas foram confirmadas na Safe!")
                                            print(f"      -> Posição assumida com sucesso para gestão quantitativa!")
                                        else:
                                            print(f"      [❌ ERRO AO EXECUTAR ORDEM REAL]: {order_res.get('error')}")
                                else:
                                    # EXECUÇÃO PAPER HIPER-REALISTA
                                    shares = round(target_stake / exec_price, 4)
                                    self.balance -= target_stake

                                    self.current_open_position = {
                                        "window_ts": window_ts,
                                        "time_str": dt_str,
                                        "market_slug": market_slug,
                                        "token_id": target_token,
                                        "direction": candidate_side,
                                        "strike": strike,
                                        "entry_price": exec_price,
                                        "shares": shares,
                                        "stake": target_stake,
                                        "entry_time": cur_time,
                                        "clob_spread": spread,
                                        "clob_best_bid": best_bid,
                                        "clob_best_ask": best_ask,
                                        "mode": "PAPER"
                                    }

                                    print(f"\n   🚀 [ORDEM PAPER PREENCHIDA NO LIVRO REAL!]:")
                                    print(f"      Lado: {candidate_side} | Preço Taker VWAP: ${exec_price:.4f}")
                                    print(f"      Cotas: {shares} | Investimento: ${target_stake:.2f} USD")
                                    print(f"      Saldo Restante: ${self.balance:,.2f} USD")

            # -------------------------------------------------------------
            # 3. MONITORAMENTO DE TAKE-PROFIT ANTECIPADO (SirMartingale) E STOP-LOSS
            # -------------------------------------------------------------
            if self.current_open_position is not None:
                pos = self.current_open_position
                cur_target_book = get_clob_orderbook(pos["token_id"])

                if cur_target_book:
                    cur_best_bid = cur_target_book["best_bid"]
                    cur_bid_size = cur_target_book["top_bid_size"]

                    # 3A. Take Profit se cota atingir >= 86¢ e houver liquidez real para venda
                    if cur_best_bid >= TAKE_PROFIT_PRICE and cur_bid_size >= (pos["shares"] * 0.5):
                        sell_price = cur_best_bid
                        real_s = self.get_token_balance(pos["token_id"]) if self.mode == "LIVE" else pos["shares"]
                        raw_s = real_s if (real_s is not None and real_s >= 0.5) else pos["shares"]
                        sell_shares = int(raw_s * 100) / 100.0
                        tp_limit_price = max(TAKE_PROFIT_PRICE, round(cur_best_bid - 0.02, 2))

                        if self.mode == "LIVE":
                            print(f"\n💰 [ENVIANDO TAKE-PROFIT REAL NA CLOB POLYMARKET!]:")
                            print(f"   Vendendo {sell_shares:.2f} cotas de {pos['direction']} (Best Bid: ${sell_price:.2f} | Limite Aceito: ${tp_limit_price:.2f})...")
                            try:
                                if self.client:
                                    self.client.cancel_all()
                            except Exception:
                                pass
                            tp_res = self.place_live_order(pos["token_id"], "SELL", sell_shares, price=tp_limit_price)
                            if tp_res.get("status") == "SUCCESS":
                                resp_data = tp_res.get("response", {})
                                tp_order_id = resp_data.get("orderID") or "N/A"
                                tp_hashes = resp_data.get("transactionsHashes") or []
                                resp_tp_p = resp_data.get("price")
                                actual_tp_price = resp_tp_p if (resp_tp_p is not None and resp_tp_p > 0) else sell_price
                                if self.client:
                                    fill = self.get_latest_clob_fill(pos["token_id"], side="SELL", min_timestamp=window_ts)
                                    if fill:
                                        actual_tp_price = fill["price"]
                                        tp_tx = fill["tx_hash"] or tp_tx
                                payout = round(sell_shares * actual_tp_price, 4)
                                pnl = round(payout - pos["stake"], 4)
                                time.sleep(1.0)
                                self.get_usdc_balance()

                                print(f"   -> TAKE-PROFIT REAL EXECUTADO! ID: {tp_order_id} | Tx: {tp_tx}")
                                print(f"   -> Cotas Vendidas @ ${actual_tp_price:.2f} | Payout: ${payout:.2f} | P&L: {pnl:+.2f} USDC | Novo Saldo: ${self.balance:,.2f} USDC")

                                self.save_journal({
                                    "cycle_ts": window_ts,
                                    "time_str": dt_str,
                                    "market_slug": pos["market_slug"],
                                    "token_id": pos["token_id"],
                                    "strike": pos["strike"],
                                    "target_side": pos["direction"],
                                    "entry_price": pos["entry_price"],
                                    "shares": sell_shares,
                                    "result": "VITÓRIA (TAKE-PROFIT CLOB REAL)",
                                    "sold_early": True,
                                    "sell_price": actual_tp_price,
                                    "payout": payout,
                                    "pnl": pnl,
                                    "order_id": tp_order_id,
                                    "tx_hash": tp_tx,
                                    "balance": round(self.balance, 4),
                                    "mode": "LIVE"
                                })
                                self.current_open_position = None
                                self.traded_windows.add(window_ts)
                                time.sleep(cur_left)
                                return
                            else:
                                print(f"   [⚠️ FALHA NO TAKE-PROFIT REAL]: {tp_res.get('error')}. Tentará novamente.")
                        else:
                            payout = round(pos["shares"] * sell_price, 4)
                            pnl = round(payout - pos["stake"], 4)
                            self.balance += payout

                            print(f"\n💰 [TAKE-PROFIT EXECUTADO NA CLOB REAL (PAPER)!]:")
                            print(f"   Venda Realizada a ${sell_price:.2f} | Payout: ${payout:.2f} | P&L: {pnl:+.2f} USD")
                            print(f"   Novo Saldo: ${self.balance:,.2f} USD")

                            self.save_journal({
                                "cycle_ts": window_ts,
                                "time_str": dt_str,
                                "market_slug": pos["market_slug"],
                                "token_id": pos["token_id"],
                                "strike": pos["strike"],
                                "target_side": pos["direction"],
                                "entry_price": pos["entry_price"],
                                "shares": pos["shares"],
                                "result": "VITÓRIA (TAKE-PROFIT CLOB REAL)",
                                "sold_early": True,
                                "sell_price": sell_price,
                                "payout": payout,
                                "pnl": pnl,
                                "balance": round(self.balance, 4),
                                "mode": "PAPER"
                            })
                            self.current_open_position = None
                            self.traded_windows.add(window_ts)
                            time.sleep(cur_left)
                            return

                    # 3B. Stop-Loss de Emergência Calibrado Anti-Whipsaw (1.8x deadband e tempo >= 200s)
                    # Exige reversão real além do micro-ruído (~9.0 bps / ~$0.11 na Solana) para evitar liquidação precipitada
                    sol_rev_threshold = round(dynamic_deadband * REVERSAL_MULTIPLIER, 4)
                    reversal = (pos["direction"] == "UP" and delta <= -sol_rev_threshold) or (pos["direction"] == "DOWN" and delta >= sol_rev_threshold)
                    if cur_elapsed >= STOP_LOSS_MIN_TIME_SEC and reversal and cur_best_bid >= STOP_LOSS_MIN_BID:
                        # Escudo Anti-Sweep (Ziad Francis SMC): Veta stop-loss se for apenas absorção transitória de liquidez (wick)
                        sweep_check = evaluate_anti_sweep_shield(
                            symbol="SOLUSDT",
                            window_ts=window_ts,
                            elapsed=cur_elapsed,
                            target_side=pos["direction"],
                            strike=pos["strike"],
                            current_spot=spot_now,
                            current_delta=delta,
                            twap_delta=None
                        )
                        if sweep_check["is_sweep"] and cur_elapsed < 265:
                            if int(cur_elapsed) % 10 < 3:
                                print(f"    [🛡️ ANTI-SWEEP SHIELD (ZIAD ALGO)]: Veto de Stop-Loss na Solana aos {cur_elapsed:.0f}s! {sweep_check['reason']}")
                            time.sleep(2)
                            continue

                        sell_price = cur_best_bid
                        real_s = self.get_token_balance(pos["token_id"]) if self.mode == "LIVE" else pos["shares"]
                        raw_s = real_s if (real_s is not None and real_s >= 0.5) else pos["shares"]
                        sell_shares = int(raw_s * 100) / 100.0
                        sl_limit_price = max(STOP_LOSS_MIN_BID, round(cur_best_bid - 0.02, 2))

                        if self.mode == "LIVE":
                            print(f"\n🚨 [ENVIANDO STOP-LOSS DE EMERGÊNCIA REAL!]:")
                            print(f"   Delta reverteu além da tolerância ({delta:+.3f} vs limiar +/-${sol_rev_threshold:.3f}). Vendendo {sell_shares:.2f} cotas (Best Bid: ${sell_price:.2f} | Limite: ${sl_limit_price:.2f})...")
                            try:
                                if self.client:
                                    self.client.cancel_all()
                            except Exception:
                                pass
                            sl_res = self.place_live_order(pos["token_id"], "SELL", sell_shares, price=sl_limit_price)
                            if sl_res.get("status") == "SUCCESS":
                                resp_data = sl_res.get("response", {})
                                sl_order_id = resp_data.get("orderID") or "N/A"
                                sl_hashes = resp_data.get("transactionsHashes") or []
                                resp_sl_p = resp_data.get("price")
                                actual_sl_price = resp_sl_p if (resp_sl_p is not None and resp_sl_p > 0) else sell_price
                                if self.client:
                                    fill = self.get_latest_clob_fill(pos["token_id"], side="SELL", min_timestamp=window_ts)
                                    if fill:
                                        actual_sl_price = fill["price"]
                                        sl_tx = fill["tx_hash"] or sl_tx
                                payout = round(sell_shares * actual_sl_price, 4)
                                pnl = round(payout - pos["stake"], 4)
                                time.sleep(1.0)
                                self.get_usdc_balance()

                                print(f"   -> STOP-LOSS REAL EXECUTADO! ID: {sl_order_id} | Tx: {sl_tx}")
                                print(f"   -> Cotas Vendidas @ ${actual_sl_price:.2f} | Saldo Resgatado: ${payout:.2f} | P&L: {pnl:+.2f} USDC | Novo Saldo: ${self.balance:,.2f} USDC")

                                self.save_journal({
                                    "cycle_ts": window_ts,
                                    "time_str": dt_str,
                                    "market_slug": pos["market_slug"],
                                    "token_id": pos["token_id"],
                                    "strike": pos["strike"],
                                    "target_side": pos["direction"],
                                    "entry_price": pos["entry_price"],
                                    "shares": sell_shares,
                                    "result": "DEFESA (STOP-LOSS CLOB REAL)",
                                    "sold_early": True,
                                    "sell_price": actual_sl_price,
                                    "payout": payout,
                                    "pnl": pnl,
                                    "order_id": sl_order_id,
                                    "tx_hash": sl_tx,
                                    "balance": round(self.balance, 4),
                                    "mode": "LIVE"
                                })
                                self.current_open_position = None
                                self.traded_windows.add(window_ts)
                                time.sleep(cur_left)
                                return
                        else:
                            payout = round(pos["shares"] * sell_price, 4)
                            pnl = round(payout - pos["stake"], 4)
                            self.balance += payout

                            print(f"\n🚨 [STOP-LOSS EXECUTADO (PAPER)!]:")
                            print(f"   Venda Realizada a ${sell_price:.2f} | Saldo Resgatado: ${payout:.2f} | P&L: {pnl:+.2f} USD")

                            self.save_journal({
                                "cycle_ts": window_ts,
                                "time_str": dt_str,
                                "market_slug": pos["market_slug"],
                                "token_id": pos["token_id"],
                                "strike": pos["strike"],
                                "target_side": pos["direction"],
                                "entry_price": pos["entry_price"],
                                "shares": pos["shares"],
                                "result": "DEFESA (STOP-LOSS CLOB REAL)",
                                "sold_early": True,
                                "sell_price": sell_price,
                                "payout": payout,
                                "pnl": pnl,
                                "balance": round(self.balance, 4),
                                "mode": "PAPER"
                            })
                            self.current_open_position = None
                            self.traded_windows.add(window_ts)
                            time.sleep(cur_left)
                            return

            time.sleep(2)

        # -------------------------------------------------------------
        # 4. APURAÇÃO FINAL NO FECHAMENTO DA VELA (300s)
        # -------------------------------------------------------------
        if self.current_open_position is not None:
            pos = self.current_open_position
            # Aguarda 4s pós-fechamento para estabilização
            time.sleep(4)
            final_spot = get_chainlink_sol_price() or get_binance_sol_spot() or spot_now
            is_win = (final_spot >= pos["strike"]) if pos["direction"] == "UP" else (final_spot < pos["strike"])
            winner = "UP" if final_spot >= pos["strike"] else "DOWN"

            payout = round(pos["shares"] * 1.00, 4) if is_win else 0.00
            pnl = round(payout - pos["stake"], 4)

            if self.mode == "LIVE":
                if is_win:
                    print("   -> Aguardando liquidação oficial do payout na Polymarket...")
                    time.sleep(8)
                self.get_usdc_balance()
            else:
                self.balance += payout

            res_str = "VITÓRIA" if is_win else "DERROTA"

            print(f"\n🏁 [APURAÇÃO FINAL SOLANA 5M]:")
            print(f"   Strike: ${pos['strike']:.2f} | Final Spot: ${final_spot:.2f} | Vencedor: {winner}")
            print(f"   Resultado: {res_str} | Payout: ${payout:.2f} | P&L Ciclo: {pnl:+.2f} USD")
            print(f"   Saldo Atualizado ({self.mode}): ${self.balance:,.2f} USD")

            self.save_journal({
                "cycle_ts": window_ts,
                "time_str": dt_str,
                "market_slug": pos["market_slug"],
                "token_id": pos["token_id"],
                "strike": pos["strike"],
                "final_spot": final_spot,
                "target_side": pos["direction"],
                "entry_price": pos["entry_price"],
                "shares": pos["shares"],
                "winner": winner,
                "result": res_str,
                "sold_early": False,
                "payout": payout,
                "pnl": pnl,
                "order_id": pos.get("order_id", "N/A"),
                "tx_hash": pos.get("tx_hash", "N/A"),
                "balance": round(self.balance, 4),
                "mode": self.mode
            })
            self.current_open_position = None
            self.traded_windows.add(window_ts)

    def start(self):
        lock_path = os.path.join(BASE_DIR, "sol_trader.lock")
        self.lock_file = _acquire_instance_lock(lock_path)
        print(f"-> Instance Lock adquirido com sucesso: {lock_path}")
        print("\n" + "=" * 90)
        print("  INICIANDO BOT SOLANA 5-MINUTE ALGO TRADER (POLYMARKET CLOB)")
        print(f"  Modo Ativo: {self.mode} (LIVRO L2 REAL CONECTADO)")
        print(f"  Funder da Conta: {POLY_FUNDER_ADDRESS}")
        print(f"  Saldo Atual ({self.mode}): ${self.balance:.2f} USD")
        print("=" * 90)
        try:
            while True:
                try:
                    self.run_cycle()
                except Exception as e:
                    print(f"[Erro no ciclo Solana]: {e}")
                time.sleep(3)
        finally:
            if hasattr(self, 'lock_file') and self.lock_file:
                try:
                    self.lock_file.close()
                except Exception:
                    pass
                try:
                    if os.path.exists(lock_path):
                        os.remove(lock_path)
                except Exception:
                    pass
            print("-> Instance Lock da Solana liberado com sucesso.")

def _acquire_instance_lock(lock_path: str):
    """Garante que apenas uma instancia do Desk 2 esteja rodando por vez"""
    if sys.platform == "win32":
        import msvcrt
        f = open(lock_path, "w")
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            return f
        except OSError:
            print("\n[ERRO FATAL] Outra instancia do Desk 2 (SOL) ja esta rodando (lock ativo). Abortando para evitar ordens duplicadas em dinheiro real.")
            sys.exit(1)
    else:
        import fcntl
        f = open(lock_path, "w")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except IOError:
            print("\n[ERRO FATAL] Outra instancia do Desk 2 (SOL) ja esta rodando (lock ativo). Abortando.")
            sys.exit(1)

# Aliases de compatibilidade
SolanaPaperTrader5M = SolanaTrader5M

if __name__ == "__main__":
    bot = SolanaTrader5M()
    bot.start()
