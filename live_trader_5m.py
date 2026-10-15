"""
Engine de Execucao Real (Live Trading V2) - Polymarket BTC 5-Minute Algo Trader
================================================================================
- Protocolo Oficial: CLOB V2 API com Smart Wallet / Poly1271 Signature
- Gestao de Risco Estrita:
  * Banca Inicial Depositada: ~21.00 USDC
  * Aposta Fixa: 1.00 USDC por ciclo
  * Circuit Breaker Stop Loss: -5.00 USDC (protecao de capital)
  * Circuit Breaker Take Profit: +10.00 USDC (garantia de lucro)
- Estrategia Quantitativa:
  * Avaliacao aos 135s (2m15s da vela)
  * Drift Intra-Vela (|Delta| >= $18.00) com Confirmacao de Tendencia
  * Streak Snapper / Reversao DDD Desativados permanentemente (Auditoria 5 Anos: WR 37.2%)
  * Execucao a mercado (FAK) via CLOB V2 API
"""
import os
import sys

# Garante suporte a UTF-8 no stdout/stderr do Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import time
import json
import csv
import urllib.request
import threading
import queue
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
import math
from risk_gate import (
    is_system_halted,
    atomic_write_json,
    check_pre_trade_gate,
    validate_executable_edge_gate,
    compute_dynamic_stake,
    get_dynamic_deadband_gate,
    check_order_flow_imbalance_gate,
    check_altcoin_market_breadth_gate,
    check_asia_session_drift_gate,
    validate_clob_spread_gate,
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

from py_clob_client_v2 import (
    ClobClient,
    SignatureTypeV2,
    MarketOrderArgsV2,
    OrderArgsV2,
    OrderType,
    BalanceAllowanceParams,
    AssetType
)
from binance_liquidation_watcher import get_liquidation_watcher
from binance_cvd_watcher import get_cvd_watcher
from py_clob_client_v2.order_builder.builder import ROUNDING_CONFIG
from anti_sweep_shield import evaluate_anti_sweep_shield
from variable_bench import bench
from jev_microstructure_gate import jev_gate

# Patch de precisao do py_clob_client_v2:
# O CLOB da Polymarket aceita no maximo 4 casas decimais no takerAmount para market buy orders.
# Para tick_size 0.001/0.0001, o SDK original define amount=5/6, gerando erro 400 (invalid amounts).
for _ts in ROUNDING_CONFIG:
    ROUNDING_CONFIG[_ts].amount = min(4, ROUNDING_CONFIG[_ts].amount)

# Caminhos dos arquivos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
JOURNAL_CSV = os.path.join(BASE_DIR, "live_trading_journal.csv")
JOURNAL_JSON = os.path.join(BASE_DIR, "live_trading_journal.json")

# Configuracoes de Risco e Estrategia Quantitativa (Modo Sniper Purista - Holdout WR 74.4%)
FIXED_STAKE = 1.00        # $1.00 USDC por aposta primaria
PRIMARY_MIN_PRICE = 0.40  # Preco minimo de cota primaria (JEV: elimina cotas de cauda com spread punitivo na CLOB)
PRIMARY_MAX_PRICE = 0.55  # Preco maximo de cota primaria (Audit Jev: teto estrito <= 0.55 elimina trades de baixo retorno e eleva EV para +$0.421)
DEADBAND_BPS = 0.00021    # 2.1 bps (0.021%) do Strike (Deadband dinâmico e scale-invariant independente do preço do BTC)
DEADBAND_MIN_FLOOR = 15.0 # Piso mínimo absoluto em USD para evitar micro-ruído
HEDGE_STAKE = 1.00        # $1.00 USDC para hedge dinamico estilo Bonereaper (min size Polymarket CLOB)
HEDGE_DELTA_THRESHOLD = 18.0  # Reversao expressiva no Chainlink aciona protecao antecipada (evita micro-ruido de repique)
HEDGE_MAX_PRICE = 0.45     # Preco maximo permitido para hedge (<= $0.45 garante retorno positivo se hedged)
STOP_LOSS_MIN_BID = 0.15   # Preco minimo de bid para liquidar posicao perdedora antecipadamente (Stop-Loss)
TAKE_PROFIT_PRICE_THRESHOLD = 0.86 # Add-on 1 (SirMartingale): Venda antecipada se cotacao bater $0.86+ (lucro ~80%)
SCOUR_ENABLED = False     # Sweeper desativado (Audit Backtest provou EV negativo de -1.8c/$)
SCOUR_DELTA_THRESHOLD = 25.0 # Delta minimo para Sweeper (se habilitado)
SCOUR_MIN_PRICE = 0.50       # Preco minimo de cota para o Sweeper
SCOUR_MAX_PRICE = 0.75       # Preco maximo de cota para o Sweeper
MAX_LOSS_LIMIT = -5.00    # Stop loss diario (-$5.00 USDC)
TAKE_PROFIT_LIMIT = 50.00 # Take profit aumentado para +$50.00 USDC
DRAWDOWN_FLOOR_USDC = 15.00 # Piso absoluto de preservacao de capital ($15.00 USDC)
MAX_SESSION_DRAWDOWN = 4.00 # Perda maxima permitida na sessao ($4.00 USDC)
MAX_ORACLE_STRIKE_DISCREPANCY_BPS = 0.0014 # Teto dinâmico de 14 bps (~$116 a $83k BTC / JEV Consensus 100%)
MAX_ORACLE_STRIKE_DISCREPANCY_FLOOR_USD = 85.00 # Piso mínimo absoluto em USD para absorver basis natural Binance vs Chainlink

def load_env_config() -> Dict[str, str]:
    """Carrega variaveis do arquivo .env"""
    cfg = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    return cfg

def get_shared_wallet_sol_impact() -> float:
    """
    Calcula o impacto financeiro acumulado (lucro/prejuízo líquido real) das operações
    compartilhadas (Desk 2 SOL e Desk 3B BTC 15m) na carteira Polygon Safe compartilhada,
    para isolar a contabilidade do Desk 1.
    """
    total_shared_pnl = 0.0
    for j_name in ["sol_trading_journal.json", "desk3b_btc15m_live_journal.json"]:
        j_path = os.path.join(BASE_DIR, j_name)
        if not os.path.exists(j_path):
            continue
        try:
            with open(j_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            mode = str(data.get("mode", "")).upper()
            if "LIVE" in mode:
                for t in data.get("trades", []):
                    total_shared_pnl += float(t.get("pnl", 0.0))
        except Exception:
            pass
    return round(total_shared_pnl, 2)

def _atomic_json_write(path: str, data: dict):
    """Grava JSON de forma atomica usando modulo central risk_gate"""
    return atomic_write_json(path, data)

def _acquire_instance_lock(lock_path: str):
    """Garante que apenas uma instancia do bot esteja rodando por vez"""
    if sys.platform == "win32":
        import msvcrt
        f = open(lock_path, "w")
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            return f
        except OSError:
            print("\n[ERRO FATAL] Outra instancia do bot ja esta rodando (lock ativo). Abortando.")
            sys.exit(1)
    else:
        import fcntl
        f = open(lock_path, "w")
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except OSError:
            print("\n[ERRO FATAL] Outra instancia do bot ja esta rodando (lock ativo). Abortando.")
            sys.exit(1)

GEOBLOCK_CACHE: Dict[str, Any] = {"timestamp": 0.0, "data": None}

def check_geoblock() -> Dict[str, Any]:
    """Verifica se o IP atual e elegivel para negociar no Polymarket (com cache de 30 min)"""
    global GEOBLOCK_CACHE
    now = time.time()
    if GEOBLOCK_CACHE["data"] and (now - GEOBLOCK_CACHE["timestamp"]) < 1800:
        return GEOBLOCK_CACHE["data"]

    try:
        req = urllib.request.Request("https://polymarket.com/api/geoblock", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read().decode())
            GEOBLOCK_CACHE = {"timestamp": now, "data": data}
            return data
    except Exception as e:
        data = {"blocked": False, "error": str(e), "country": "UNKNOWN"}
        GEOBLOCK_CACHE = {"timestamp": now, "data": data}
        return data

def get_binance_spot() -> Optional[float]:
    """Busca preco spot BTC/USDT de referencia na Binance"""
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

def get_chainlink_price() -> Optional[float]:
    """
    Consulta a cotacao oficial do Oraculo Chainlink BTC/USD (8 decimais)
    diretamente no contrato AggregatorV3 da Polygon (0xc907E116054Ad103354f2D350FD2514433D57F6f)
    usando eth_call (latestRoundData selector 0xfeaf968c). Zero gas e sub-segundo.
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
            {"to": "0xc907E116054Ad103354f2D350FD2514433D57F6f", "data": "0xfeaf968c"},
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
                    if price > 10000:
                        return round(price, 2)
        except Exception:
            continue

    # Se todas as RPCs da Polygon falharem, retorna None em vez de mascarar com Binance spot
    print("   [ALERTA RPC] Todas as RPCs Polygon para Oraculo Chainlink falharam nesta chamada.")
    return None

def get_candle_open(window_ts: int) -> Optional[float]:
    """Fallback: Busca preco de abertura da vela de 5m na Binance se necessario"""
    url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=3"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            klines = json.loads(r.read().decode())
            for k in klines:
                if int(k[0]) // 1000 == window_ts:
                    return float(k[1])
            if klines:
                return float(klines[-1][1])
    except Exception:
        pass
    return None

def get_polymarket_market(window_ts: int) -> Optional[Dict[str, Any]]:
    """Busca mercado 5m correspondente a janela na Gamma API"""
    slug = f"btc-updown-5m-{window_ts}"
    url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PolymarketLiveBot/2.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read().decode())
            if data and len(data) > 0:
                return data[0]
    except Exception as e:
        print(f"[Poly API Error {slug}]: {e}")
    return None

def get_clob_orderbook(token_id: str) -> Optional[Dict[str, Any]]:
    """
    Consulta o Order Book L2 completo diretamente da CLOB da Polymarket
    e extrai metricas de microestrutura (PolyResearch Robotics methodology):
    - best_bid, best_ask
    - spread
    - top_imbalance (L1) e depth_imbalance (profundidade total)
    - microprice (Stoikov volume-weighted fair price)
    """
    url = f"https://clob.polymarket.com/book?token_id={token_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PolymarketLiveBot/2.0"})
        with urllib.request.urlopen(req, timeout=3.5) as r:
            book = json.loads(r.read().decode())
            bids = [(float(b["price"]), float(b["size"])) for b in book.get("bids", []) if "price" in b and "size" in b and float(b["size"]) >= 1.0]
            asks = [(float(a["price"]), float(a["size"])) for a in book.get("asks", []) if "price" in a and "size" in a and float(a["size"]) >= 1.0]

            if not bids or not asks:
                return None

            best_bid_item = max(bids, key=lambda x: x[0])
            best_ask_item = min(asks, key=lambda x: x[0])

            best_bid, top_bid_size = best_bid_item[0], best_bid_item[1]
            best_ask, top_ask_size = best_ask_item[0], best_ask_item[1]

            spread = best_ask - best_bid
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
                "top_imbalance": round(top_imbalance, 4),
                "depth_imbalance": round(depth_imbalance, 4),
                "microprice": round(microprice, 4),
                "bids_raw": bids,
                "asks_raw": asks
            }
    except Exception as e:
        print(f"    [Erro ao consultar Order Book CLOB]: {e}")
        return None

# [NOTA DE ARQUITETURA]: Módulos Streak Snapper e Reversão Markoviana DDD foram aposentados
# após a Auditoria Quantitativa dos Últimos 5 Anos demonstrar WR destrutivo de 37.2%.
class CandleTWAPTracker:
    """
    Rastreador de Média Ponderada pelo Tempo (TWAP) para velas de 5 minutos (300 segundos).
    Espelha fielmente a regra oficial de liquidação da Polymarket/Chainlink:
    'TWAP of the time range specified is greater than or equal to the price at the beginning of that range'.
    """
    def __init__(self, window_ts: int, strike: float, symbol: str = "BTCUSDT"):
        self.window_ts = window_ts
        self.strike = strike
        self.symbol = symbol
        self.samples: List[Tuple[float, float]] = []  # Lista de (t_relativo_sec, preco)
        self._backfilled = False
        # Adiciona o strike oficial no segundo 0
        if strike and strike > 0:
            self.samples.append((0.0, strike))

    def backfill_from_binance(self, current_ts: float):
        """Preenche o histórico de preços caso o bot tenha iniciado a vela com atraso."""
        if self._backfilled:
            return
        elapsed = int(current_ts - self.window_ts)
        if elapsed <= 5:
            self._backfilled = True
            return

        try:
            start_ms = self.window_ts * 1000
            end_ms = int(current_ts * 1000)
            url = f"https://api.binance.com/api/v3/klines?symbol={self.symbol}&interval=1m&startTime={start_ms}&endTime={end_ms}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3.0) as r:
                klines = json.loads(r.read().decode())
                for k in klines:
                    k_start = (k[0] / 1000.0) - self.window_ts
                    o, h, l, c = float(k[1]), float(k[2]), float(k[3]), float(k[4])
                    typ = (o + h + l + c) / 4.0
                    for offset in [0.0, 15.0, 30.0, 45.0]:
                        t_sec = k_start + offset
                        if 0.0 <= t_sec <= elapsed:
                            self.samples.append((t_sec, typ))
            self.samples.sort(key=lambda x: x[0])
            self._backfilled = True
        except Exception:
            self._backfilled = True

    def add_sample(self, price: float, current_ts: Optional[float] = None):
        """Registra uma cotação instantânea no tempo relativo da vela."""
        if not price or price <= 0:
            return
        ts = current_ts if current_ts is not None else time.time()
        t_rel = max(0.0, min(300.0, ts - self.window_ts))
        self.samples.append((t_rel, price))

    def get_current_twap(self) -> float:
        """Calcula o TWAP acumulado até o momento via integração trapezoidal ponderada."""
        if not self.samples:
            return self.strike
        if len(self.samples) == 1:
            return self.samples[0][1]

        sorted_samples = sorted(self.samples, key=lambda x: x[0])
        total_time = 0.0
        weighted_sum = 0.0

        for i in range(len(sorted_samples) - 1):
            t1, p1 = sorted_samples[i]
            t2, p2 = sorted_samples[i+1]
            dt = max(0.001, t2 - t1)
            avg_p = (p1 + p2) / 2.0
            weighted_sum += avg_p * dt
            total_time += dt

        if total_time <= 0:
            return sorted_samples[-1][1]

        return weighted_sum / total_time

    def get_twap_delta(self) -> float:
        """Retorna a diferença entre o TWAP atual e o Strike (K)."""
        return self.get_current_twap() - self.strike

    def get_required_spot_to_win(self, target_side: str, at_elapsed_sec: float) -> Optional[float]:
        """
        Calcula o preço spot médio necessário nos segundos restantes (até 300s)
        para que a média TWAP final termine vencedora no oráculo.
        """
        cur_twap = self.get_current_twap()
        t = max(1.0, min(295.0, at_elapsed_sec))
        remaining = 300.0 - t
        if remaining <= 3.0:
            return None

        # Condição de vitória no TWAP final de 300s:
        # Para UP: TWAP >= strike -> (t * cur_twap + remaining * req_spot) / 300 >= strike
        # req_spot = (300 * strike - t * cur_twap) / remaining
        req_spot = (300.0 * self.strike - t * cur_twap) / remaining
        return req_spot


def get_polymarket_resolution(window_ts: int, max_retries: int = 15) -> Optional[str]:
    """
    Busca o resultado oficial apurado pelo Polymarket para o mercado btc-updown-5m-{window_ts}.
    Apenas considera resolvido quando outcomePrices atingir >= 0.98 (liquidação oficial),
    aguardando até 45s para que o relayer da Polymarket processe a média TWAP de 60s.
    """
    slug = f"btc-updown-5m-{window_ts}"
    url = f"https://gamma-api.polymarket.com/events?slug={slug}"

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PolymarketSettler/2.0"})
            with urllib.request.urlopen(req, timeout=3.5) as r:
                data = json.loads(r.read().decode("utf-8"))
                if data and "markets" in data[0] and len(data[0]["markets"]) > 0:
                    m = data[0]["markets"][0]
                    prices_str = m.get("outcomePrices")
                    if prices_str:
                        prices = [float(p) for p in json.loads(prices_str)]
                        if len(prices) >= 2:
                            p_up, p_down = prices[0], prices[1]
                            # Limite estrito de liquidação oficial (0.98+)
                            if p_up >= 0.98:
                                return "UP"
                            elif p_down >= 0.98:
                                return "DOWN"
        except Exception:
            pass
        if attempt < max_retries - 1:
            time.sleep(3.0)
    return None

class LiveTrader:
    def __init__(self):
        self.cfg = load_env_config()
        self.private_key = self.cfg.get("POLYGON_PRIVATE_KEY", "").strip()
        if self.private_key.startswith("0x"):
            self.private_key = self.private_key[2:]
        self.funder_address = self.cfg.get("POLY_FUNDER_ADDRESS", "").strip()
        self.signer_address = self.cfg.get("POLY_SIGNER_ADDRESS", "").strip()

        self.client: Optional[ClobClient] = None
        self.candle_strikes: Dict[int, float] = {}
        self.binance_opens: Dict[int, float] = {}
        self.initial_deposit = 21.00 # Deposito original em USDC
        self.session_initial_balance = 0.0
        self.current_balance = 0.0
        self.session_pnl = 0.0
        self.session_pnl_trades = 0.0
        self.session_cycles = 0
        self.session_wins = 0
        self.session_losses = 0
        self.cumulative_cycle_pnl = 0.0
        self.pending_unredeemed_payouts = 0.0
        self.session_pending_unredeemed = 0.0

        self.total_spent = 0.0
        self.total_pnl = 0.0
        self.wins = 0
        self.losses = 0
        self.cycles_executed = 0
        self.recent_winners = []
        self.is_halted = False
        self.halt_reason = ""
        self.liq_watcher = get_liquidation_watcher()
        self.cvd_watcher = get_cvd_watcher()

        self.execution_mode = self.cfg.get("EXECUTION_MODE", "paper").lower()
        if self.execution_mode == "paper":
            self.journal_json = os.path.join(BASE_DIR, "paper_trading_journal.json")
            self.journal_csv = os.path.join(BASE_DIR, "paper_trading_journal.csv")
        else:
            self.journal_json = JOURNAL_JSON
            self.journal_csv = JOURNAL_CSV

        self.lock_file = None
        self.journal_lock = threading.Lock()
        self.traded_windows = self._load_traded_windows()
        self._init_journal()
        self._init_clob()
        self._start_async_reconciler()

    def _load_traded_windows(self) -> set:
        """Carrega todas as janelas (window_ts) ja negociadas para evitar duplicacoes no restart"""
        traded = set()
        if os.path.exists(self.journal_json):
            try:
                with open(self.journal_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for t in data.get("trades", []):
                    w = t.get("window_ts")
                    if w:
                        traded.add(int(w))
            except Exception:
                pass
        return traded

    def _init_journal(self):
        """Inicializa arquivos de auditoria se nao existirem"""
        if not os.path.exists(self.journal_csv):
            with open(self.journal_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "cycle_num", "window_ts", "strike_K", "entry_spot",
                    "delta_entry", "decision", "token_id", "order_id", "status",
                    "tx_hash", "entry_price", "shares", "final_spot", "winner", "result",
                    "payout", "cycle_pnl", "total_pnl", "balance",
                    "hedged", "hedge_decision", "hedge_tx_hash", "hedge_shares", "hedge_payout",
                    "early_sold", "early_sell_price", "scour_executed", "scour_side", "scour_tx_hash"
                ])

        if os.path.exists(self.journal_json):
            try:
                with open(self.journal_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.total_spent = data.get("total_spent", 0.0)
                    self.wins = data.get("wins", 0)
                    self.losses = data.get("losses", 0)
                    self.cycles_executed = data.get("cycles_executed", 0)
                    self.pending_unredeemed_payouts = float(data.get("pending_unredeemed_payouts", 0.0))
                    trades = data.get("trades", [])
                    self.cumulative_cycle_pnl = round(sum(float(t.get("cycle_pnl", 0.0)) for t in trades), 2)
                    self.recent_winners = [r["winner"] for r in trades[-5:] if r.get("winner")]
            except Exception as ej:
                print(f"[ALERTA CRÍTICO] Falha ao ler {self.journal_json}: {ej}. Criando backup de seguranca.")
                try:
                    os.replace(self.journal_json, f"{self.journal_json}.corrupt-{int(time.time())}")
                except Exception:
                    pass

    def _init_clob(self):
        """Configura e autentica o cliente CLOB V2 Polymarket com Poly1271"""
        if self.execution_mode == "paper":
            print("-> [MODO PAPER ATIVO]: Nenhuma ordem real sera enviada para a CLOB. Operando em simulacao limpa.")
            self.client = None
            bal = 20.00
            self.session_initial_balance = bal
            self.current_balance = bal
            print(f"   -> Saldo Simulado em Carteira: ${bal:.2f} USDC (Modo Paper)")
            return

        if not self.private_key:
            print("[ERRO FATAL] POLYGON_PRIVATE_KEY nao configurada no .env!")
            sys.exit(1)

        print(f"-> Inicializando ClobClient V2 (Funder Safe: {self.funder_address})...")
        try:
            self.client = ClobClient(
                host="https://clob.polymarket.com",
                key=self.private_key,
                chain_id=137,
                signature_type=SignatureTypeV2.POLY_1271,
                funder=self.funder_address
            )
            creds = self.client.derive_api_key()
            self.client.set_api_creds(creds)
            print("   -> Conexao L1/L2 com Polymarket CLOB V2 estabelecida com sucesso!")

            # Verificacao de Geoblock
            geo = check_geoblock()
            ip = geo.get("ip", "desconhecido")
            country = geo.get("country", "??")
            if geo.get("blocked", False):
                print(f"   [!] ALERTA GEOBLOCK: IP ({ip}, Pais: {country}) esta BLOQUEADO!")
                print("       Conecte a NordVPN a Portugal antes de operar.")
            else:
                print(f"   -> Geoblock Status: LIBERADO! IP: {ip} | Pais: {country} (Apto para operar)")

            # Atualiza saldo real da carteira
            bal = self.get_usdc_balance()
            if os.path.exists(self.journal_json):
                try:
                    with open(self.journal_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.session_initial_balance = float(data.get("session_initial_balance", bal))
                except Exception:
                    self.session_initial_balance = bal
            else:
                self.session_initial_balance = bal
            self.current_balance = bal
            if bal > 0 and os.path.exists(self.journal_json):
                try:
                    with open(self.journal_json, "r", encoding="utf-8") as f:
                        jdata = json.load(f)
                    jdata["current_balance"] = round(bal, 4)
                    jdata["total_pnl_vs_deposit"] = round(bal - self.initial_deposit, 2)
                    jdata["session_pnl"] = round(bal - self.session_initial_balance, 2)
                    jdata["last_updated"] = datetime.now().isoformat()
                    _atomic_json_write(self.journal_json, jdata)
                except Exception:
                    pass
            print(f"   -> Saldo Real em Carteira: ${bal:.2f} USDC (Base de Risco Inicial da Sessao: ${self.session_initial_balance:.2f})")
        except Exception as e:
            print(f"[ERRO ao autenticar ClobClient]: {e}")
            self.client = None

    def _start_async_reconciler(self):
        """Inicia thread de reconciliacao assincrona em segundo plano"""
        self.reconciliation_queue = queue.Queue()
        self.reconciler_thread = threading.Thread(target=self._async_reconciliation_worker, daemon=True, name="AsyncReconciler")
        self.reconciler_thread.start()
        print("   -> Thread de Reconciliacao Assincrona com Oraculo Polymarket iniciada com sucesso!")

    def _async_reconciliation_worker(self):
        """Monitora e reconcilia trades com o oraculo oficial Polymarket apos a consolidacao do TWAP"""
        while True:
            try:
                item = self.reconciliation_queue.get()
                if not item:
                    continue

                cycle_num = item["cycle"]
                window_ts = item["window_ts"]
                tentative_winner = item["tentative_winner"]
                target_side = item.get("target_side")
                has_primary = item.get("has_primary", False)
                sold_early = item.get("sold_early", False)
                early_sell_payout = item.get("early_sell_payout", 0.0)
                shares = item.get("shares", 0.0)
                hedged = item.get("hedged", False)
                hedge_side = item.get("hedge_side")
                hedge_shares = item.get("hedge_shares", 0.0)
                scour_executed = item.get("scour_executed", False)
                scour_side = item.get("scour_side")
                scour_shares = item.get("scour_shares", 0.0)
                total_stake = item.get("total_stake", 1.0)

                # Aguarda ate 120s apos o fechamento da vela para a Polymarket processar o TWAP de 60s
                candle_close_time = window_ts + 300
                wait_until = candle_close_time + 120
                now = time.time()
                if now < wait_until:
                    time.sleep(wait_until - now)

                # Tenta obter a resolucao oficial por ate 15 tentativas (com 10s de intervalo = 150s adicionais)
                official_winner = None
                for _ in range(15):
                    official_winner = get_polymarket_resolution(window_ts, max_retries=1)
                    if official_winner:
                        break
                    time.sleep(10.0)

                if not official_winner:
                    continue

                # Se o oraculo oficial divergir do provisorio:
                if official_winner != tentative_winner:
                    print(f"\n    [🔄 RECONCILIADOR ASSÍNCRONO]: Divergência detectada no Ciclo #{cycle_num}!")
                    print(f"       Provisório: {tentative_winner} -> Oficial Polymarket: {official_winner}")

                    if sold_early:
                        payout_primary = early_sell_payout
                    elif has_primary:
                        primary_win = (target_side == official_winner)
                        payout_primary = round(shares * 1.00, 2) if primary_win else 0.00
                    else:
                        payout_primary = 0.00

                    hedge_win = (hedged and hedge_side == official_winner)
                    payout_hedge = round(hedge_shares * 1.00, 2) if hedge_win else 0.00

                    scour_win = (scour_executed and scour_side == official_winner)
                    payout_scour = round(scour_shares * 1.00, 2) if scour_win else 0.00

                    new_total_payout = round(payout_primary + payout_hedge + payout_scour, 2)
                    new_cycle_pnl = round(new_total_payout - total_stake, 2)

                    if sold_early and scour_executed:
                        new_res_str = "VITORIA DUPLA (TP + SCOUR)"
                    elif sold_early:
                        new_res_str = "VITORIA (TAKE PROFIT ANTECIPADO)" if new_cycle_pnl >= 0 else "DEFESA (STOP LOSS ANTECIPADO)"
                    elif scour_executed and not (has_primary or sold_early):
                        new_res_str = "VITORIA (SCOUR SWEEPER)" if scour_win else "DERROTA (SCOUR SWEEPER)"
                    elif hedged:
                        new_res_str = "VITORIA (HEDGE)" if new_cycle_pnl >= 0 else "DEFESA (PERDA MINIMIZADA)"
                    elif new_cycle_pnl >= 0:
                        new_res_str = "VITORIA"
                    else:
                        new_res_str = "DERROTA"

                    time.sleep(2.0)
                    real_bal = self.get_usdc_balance()

                    with self.journal_lock:
                        if os.path.exists(self.journal_json):
                            try:
                                with open(self.journal_json, "r", encoding="utf-8") as f:
                                    jdata = json.load(f)

                                for t in jdata.get("trades", []):
                                    if t.get("cycle") == cycle_num:
                                        t["winner"] = official_winner
                                        t["winner_source"] = "POLYMARKET_OFFICIAL"
                                        t["result"] = new_res_str
                                        t["total_payout"] = new_total_payout
                                        if scour_executed:
                                            t["scour_payout"] = payout_scour
                                        t["cycle_pnl"] = new_cycle_pnl
                                        t["balance"] = real_bal
                                        break

                                total_w = sum(1 for t in jdata["trades"] if t.get("cycle_pnl", 0) >= 0)
                                total_l = sum(1 for t in jdata["trades"] if t.get("cycle_pnl", 0) < 0)
                                jdata["wins"] = total_w
                                jdata["losses"] = total_l
                                jdata["win_rate"] = round(total_w / len(jdata["trades"]) * 100, 1) if jdata["trades"] else 0.0
                                jdata["current_balance"] = real_bal
                                jdata["session_pnl"] = round(real_bal - jdata.get("session_initial_balance", real_bal), 2)
                                jdata["total_pnl_vs_deposit"] = round(real_bal - self.initial_deposit, 2)

                                _atomic_json_write(self.journal_json, jdata)

                                self.wins = total_w
                                self.losses = total_l
                                self.current_balance = real_bal
                                self.session_pnl = jdata["session_pnl"]
                                self.cumulative_cycle_pnl = round(sum(float(t.get("cycle_pnl", 0.0)) for t in jdata.get("trades", [])), 2)
                                record_desk_trade_result("desk1", is_win=(new_cycle_pnl >= 0), pnl=new_cycle_pnl)
                            except Exception as ej:
                                print(f"       [Erro ao atualizar JSON na reconciliação]: {ej}")

                        if os.path.exists(self.journal_csv):
                            try:
                                rows = []
                                with open(self.journal_csv, "r", newline="", encoding="utf-8") as f:
                                    reader = csv.reader(f)
                                    for r in reader:
                                        if len(r) > 17 and r[1] == str(cycle_num):
                                            r[14] = official_winner
                                            r[15] = new_res_str
                                            r[16] = str(new_total_payout)
                                            r[17] = str(new_cycle_pnl)
                                            r[19] = str(round(real_bal, 2))
                                        rows.append(r)
                                tmp_csv = self.journal_csv + ".tmp"
                                with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
                                    writer = csv.writer(f)
                                    writer.writerows(rows)
                                    f.flush()
                                    os.fsync(f.fileno())
                                os.replace(tmp_csv, self.journal_csv)
                            except Exception as ec:
                                print(f"       [Erro ao atualizar CSV na reconciliação]: {ec}")

                    print(f"       -> Reconciliação concluída! Resultado corrigido para: {new_res_str} | Saldo real: ${real_bal:.2f} USDC\n")
                else:
                    # Oráculo oficial confirmou o resultado provisório.
                    # Atualiza o saldo real em carteira pós-liquidação do payout pelo contrato da Polymarket
                    time.sleep(2.0)
                    real_bal = self.get_usdc_balance()
                    with self.journal_lock:
                        if os.path.exists(self.journal_json):
                            try:
                                with open(self.journal_json, "r", encoding="utf-8") as f:
                                    jdata = json.load(f)
                                for t in jdata.get("trades", []):
                                    if t.get("cycle") == cycle_num:
                                        t["winner_source"] = "POLYMARKET_OFFICIAL"
                                        t["balance"] = real_bal
                                        break
                                jdata["current_balance"] = real_bal
                                jdata["session_pnl"] = round(real_bal - jdata.get("session_initial_balance", real_bal), 2)
                                jdata["total_pnl_vs_deposit"] = round(real_bal - self.initial_deposit, 2)
                                _atomic_json_write(self.journal_json, jdata)
                                self.current_balance = real_bal
                                self.session_pnl = jdata["session_pnl"]
                            except Exception as ej:
                                print(f"       [Erro ao atualizar JSON na confirmação]: {ej}")

                        if os.path.exists(self.journal_csv):
                            try:
                                rows = []
                                with open(self.journal_csv, "r", newline="", encoding="utf-8") as f:
                                    reader = csv.reader(f)
                                    for r in reader:
                                        if len(r) > 19 and r[1] == str(cycle_num):
                                            r[19] = str(round(real_bal, 2))
                                        rows.append(r)
                                tmp_csv = self.journal_csv + ".tmp"
                                with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
                                    writer = csv.writer(f)
                                    writer.writerows(rows)
                                    f.flush()
                                    os.fsync(f.fileno())
                                os.replace(tmp_csv, self.journal_csv)
                            except Exception as ec:
                                print(f"       [Erro ao atualizar CSV na confirmação]: {ec}")

                    print(f"       -> Confirmação oficial concluída! Saldo pós-liquidação: ${real_bal:.2f} USDC\n")
            except Exception as e:
                time.sleep(5)

    def get_usdc_balance(self) -> float:
        """Consulta o saldo real de USDC na conta Polymarket via CLOB V2"""
        if self.execution_mode == "paper":
            return self.current_balance
        if not self.client:
            return 0.0
        try:
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            info = self.client.get_balance_allowance(params)
            raw_bal = float(info.get("balance", 0.0))
            bal = raw_bal / 1e6
            self.current_balance = round(bal, 4)
            return self.current_balance
        except Exception as e:
            print(f"[Aviso ao buscar saldo]: {e}")
            return -1.0

    def get_token_balance(self, token_id: str) -> float:
        """Consulta o saldo real de cotas de um token condicional na carteira Safe"""
        if self.execution_mode == "paper":
            return 0.0
        if not self.client or not token_id:
            return 0.0
        try:
            params = BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
            info = self.client.get_balance_allowance(params)
            raw_bal = float(info.get("balance", 0.0))
            return raw_bal / 1e6
        except Exception as e:
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

    def _is_past_deadline(self, window_ts: int, max_elapsed: int = 295) -> bool:
        """Retorna True se a janela estiver muito proxima do fim (evita ordens pos-fechamento)"""
        return (time.time() - window_ts) >= max_elapsed

    def _execute_emergency_stop_loss(self, target_token: str, target_side: str, shares: float, window_ts: int) -> Dict[str, Any]:
        """Tenta liquidar posicao perdedora antecipadamente na CLOB antes do fechamento"""
        if self._is_past_deadline(window_ts, 295):
            print("       [Stop-Loss] Prazo limite de 295s atingido. Ordem abortada.")
            return {"success": False}

        ob_primary = get_clob_orderbook(target_token)
        best_bid_primary = ob_primary["best_bid"] if ob_primary else 0.0
        if best_bid_primary >= STOP_LOSS_MIN_BID:
            try:
                if self.client:
                    self.client.cancel_all()
            except Exception:
                pass
            real_tok = self.get_token_balance(target_token) if self.execution_mode != "paper" else shares
            raw_s = real_tok if (real_tok is not None and real_tok >= 0.5) else shares
            sell_shares = int(raw_s * 100) / 100.0
            if sell_shares >= 0.1:
                sl_limit_price = max(STOP_LOSS_MIN_BID, round(best_bid_primary - 0.02, 2))
                print(f"    [🚨 STOP-LOSS DE EMERGENCIA]: Ha liquidez para estancar a perda! Best Bid de {target_side}: ${best_bid_primary:.2f} (>= ${STOP_LOSS_MIN_BID:.2f}).")
                print(f"       Vendendo {sell_shares:.2f} cotas de {target_side} a mercado (limite: ${sl_limit_price:.2f}) para resgatar caixa...")
                sl_res = self.place_live_order(target_token, "SELL", sell_shares, price=sl_limit_price)
                if sl_res and sl_res.get("status") == "SUCCESS":
                    sl_confirmed = True
                    if self.execution_mode != "paper":
                        time.sleep(2.0)
                        rem_tok = self.get_token_balance(target_token)
                        if rem_tok >= sell_shares:
                            # Consulta se houve trade recente de SELL antes de assumir FAK não preenchido
                            fill_check = self.get_latest_clob_fill(target_token, side="SELL", min_timestamp=window_ts)
                            if fill_check and fill_check["size"] > 0:
                                print("       -> [CLOB CONFIRMADO]: Venda de stop-loss confirmada via histórico de trades da CLOB!")
                                rem_tok = 0.0
                        if rem_tok >= sell_shares:
                            print(f"       [ALERTA STOP-LOSS] Ordem aceita pela API mas cotas continuam na carteira ({rem_tok:.2f} cotas). FAK não preenchido.")
                            sl_confirmed = False

                    if sl_confirmed:
                        s_resp = sl_res.get("response", {})
                        s_hashes = s_resp.get("transactionsHashes") or []
                        early_tx = s_hashes[0] if s_hashes else (s_resp.get("orderID") or "EXECUTED")
                        resp_price = s_resp.get("price")
                        actual_price = resp_price if (resp_price is not None and resp_price > 0) else best_bid_primary
                        actual_tx = early_tx
                        if self.execution_mode != "paper" and self.client:
                            fill = self.get_latest_clob_fill(target_token, side="SELL", min_timestamp=window_ts)
                            if fill:
                                actual_price = fill["price"]
                                actual_tx = fill["tx_hash"] or actual_tx
                        early_payout = round(sell_shares * actual_price, 2)
                        print(f"       -> STOP-LOSS EXECUTADO COM SUCESSO! Tx: {early_tx}")
                        bench.sit("desk1", "post_stop_loss_quarantine", 300)
                        print(f"       -> Preço Real de Venda: ${actual_price:.2f} | Saldo resgatado da posicao: ${early_payout:.2f} USDC (Perda estancada em -${(1.00 - early_payout):.2f})")
                        return {
                            "success": True,
                            "tx_hash": early_tx,
                            "price": actual_price,
                            "payout": early_payout,
                            "shares": sell_shares
                        }
                    else:
                        print("       -> Stop-loss não consumado no livro. Posição mantida aberta para próxima tentativa.")
                else:
                    print(f"       [Falha no stop-loss]: {sl_res.get('error') if sl_res else 'Erro desconhecido'}")
        else:
            print(f"       [Stop-loss dispensado]: Best Bid (${best_bid_primary:.2f}) < ${STOP_LOSS_MIN_BID:.2f}. Mantendo risco travado em $1.00.")
        return {"success": False}

    def place_live_order(self, token_id: str, side: str, amount: float, price: Optional[float] = None, max_price: Optional[float] = None, post_only: bool = False) -> Dict[str, Any]:
        """Cria e envia ordem real para o Polymarket CLOB V2 (BUY em USDC ou cotas, SELL em cotas; suporta post_only Maker)"""
        halted, halt_msg = is_system_halted()
        if halted:
            print(f"\n[🛑 RISK GATE VETO]: Ordem LIVE bloqueada: {halt_msg}")
            return {"status": "ERROR", "error": f"VETO_KILL_SWITCH: {halt_msg}"}

        if self.execution_mode == "paper":
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
                        actual_price = price or 0.0
                        fill = self.get_latest_clob_fill(token_id, side="SELL")
                        if fill:
                            actual_price = fill["price"]
                            actual_tx = fill["tx_hash"] or actual_tx
                        print(f"       [🚨 RECUPERAÇÃO ANTI-FANTASMA]: Venda confirmada via CLOB (cotas zeradas)! Preço Real: ${actual_price:.2f} | Tx: {actual_tx}")
                        return {
                            "status": "SUCCESS",
                            "response": {
                                "orderID": actual_tx,
                                "transactionsHashes": [actual_tx],
                                "reconciled": True,
                                "price": actual_price
                            }
                        }
                except Exception:
                    pass
            return {"status": "FAILED", "error": err_str}

    def run_trading_cycle(self):
        """Executa um ciclo de negociacao da vela atual de 5 minutos alinhado com o Oraculo Chainlink"""
        now = int(time.time())
        window_ts = now - (now % 300)
        seconds_elapsed = now - window_ts
        seconds_left = 300 - seconds_elapsed

        time_str = datetime.fromtimestamp(window_ts).strftime("%H:%M:%S")
        print(f"\n=================================================================")
        print(f"[CICLO ATIVO] Janela: {time_str} (Restam {seconds_left}s) | P&L Sessao: ${self.session_pnl:+.2f}")
        print(f"=================================================================")

        # Deduplicacao de Janela: impede reexecucao no mesmo candle de 5m em caso de restart
        if window_ts in self.traded_windows:
            print(f"    [DEDUPLICACAO] Janela {time_str} ({window_ts}) ja foi processada nesta sessao. Aguardando proximo candle...")
            wait_time = max(5, 300 - seconds_elapsed + 2)
            time.sleep(min(wait_time, 15))
            return

        # -1. Verificacao de Kill-Switch Global via Arquivo ('HALT' ou 'EMERGENCY_STOP')
        halt_file = os.path.join(BASE_DIR, "HALT")
        emergency_file = os.path.join(BASE_DIR, "EMERGENCY_STOP")
        if os.path.exists(halt_file) or os.path.exists(emergency_file):
            print(f"\n    [🚨 KILL-SWITCH GLOBAL ATIVADO]: Arquivo de emergencia ('HALT'/'EMERGENCY_STOP') detectado. Nenhuma ordem sera aberta.")
            time.sleep(10)
            return

        # 0. Protecao Mestre contra Drawdown Absoluto do Deposito ($21.00)
        MAX_TOTAL_DRAWDOWN = 6.00 # Se cair de $21.00 para <= $15.00, trava permanentemente
        cur_bal_check = self.get_usdc_balance()
        if cur_bal_check > 0 and (self.initial_deposit - cur_bal_check) >= MAX_TOTAL_DRAWDOWN:
            self.is_halted = True
            self.halt_reason = f"DRAWDOWN MESTRE ATINGIDO: Saldo (${cur_bal_check:.2f}) caiu >= ${MAX_TOTAL_DRAWDOWN:.2f} do deposito original (${self.initial_deposit:.2f})."
            print(f"\n[🚨 CIRCUIT BREAKER MESTRE]: {self.halt_reason}")
            return

        # 0.1. Verificacao de Geoblock em Tempo Real
        geo = check_geoblock()
        if geo.get("blocked", False):
            print(f"\n[GEOBLOCK BLOQUEADO]: IP {geo.get('ip')} ({geo.get('country')}) esta bloqueado para ordens!")
            print("   Certifique-se de que a NordVPN esta conectada a Portugal e aguarde...")
            time.sleep(15)
            return

        # 1. Verifica Saldo Disponivel e Conectividade
        bal = self.get_usdc_balance()
        if bal < 0:
            print("    [!] Falha de comunicacao ao consultar saldo USDC na Polygon. Pulando rodada por seguranca.")
            time.sleep(15)
            return
        print(f"    Saldo Real em Carteira: ${bal:.2f} USDC")

        # 2. Verifica limites do Circuit Breaker na Sessao Ativa
        if bal < DRAWDOWN_FLOOR_USDC:
            self.is_halted = True
            self.halt_reason = f"PISO DE CAPITAL ATINGIDO (${bal:.2f} < ${DRAWDOWN_FLOOR_USDC:.2f} USDC). Parada de emergência para proteção do patrimônio."
            print(f"\n[CIRCUIT BREAKER - DRAWDOWN FLOOR]: {self.halt_reason}")
            return

        if self.session_pnl <= -MAX_SESSION_DRAWDOWN or self.session_pnl <= MAX_LOSS_LIMIT:
            self.is_halted = True
            self.halt_reason = f"STOP LOSS DE SESSAO ATINGIDO (P&L: ${self.session_pnl:.2f} <= -${MAX_SESSION_DRAWDOWN:.2f}). Protecao de capital ativada."
            print(f"\n[CIRCUIT BREAKER - SESSION DRAWDOWN]: {self.halt_reason}")
            return

        if self.session_pnl >= TAKE_PROFIT_LIMIT:
            self.is_halted = True
            self.halt_reason = f"TAKE PROFIT DE SESSAO ATINGIDO (P&L: ${self.session_pnl:.2f} >= ${TAKE_PROFIT_LIMIT:.2f}). Lucro garantido com sucesso!"
            print(f"\n[CIRCUIT BREAKER - TAKE PROFIT]: {self.halt_reason}")
            return

        if bal < FIXED_STAKE:
            print(f"    [!] Saldo insuficiente para aposta de ${FIXED_STAKE:.2f} USDC.")
            print(f"    -> Aguardando saldo... (Pressione Ctrl+C para sair)")
            time.sleep(15)
            return

        # Checagem do Variable Bench e Disjuntores (Universal 2-Loss + Coin-Flip - JEV AI)
        is_benched, b_reason, b_rem = bench.check_consecutive_losses_breaker("desk1", self.journal_json, max_consecutive_losses=2, cooldown_seconds=1800)
        if not is_benched:
            is_benched, b_reason, b_rem = bench.check_coin_flip_breaker("desk1", self.journal_json)
        if not is_benched:
            is_benched, b_reason, b_rem = bench.is_benched("desk1")
        if is_benched:
            print(f"    [🛑 VARIABLE BENCH]: Desk 1 em cooldown ({b_reason}) — restam {b_rem:.1f}s. Aguardando...")
            time.sleep(min(15, max(2, int(b_rem))))
            return

        # 3. Busca Strike Price Oficial (Oraculo Chainlink) e Abertura Binance
        strike_captured_late = False
        if window_ts in self.candle_strikes:
            strike = self.candle_strikes[window_ts]
        else:
            if seconds_elapsed > 20:
                print(f"    [AVISO TEMPO] Entrada tardia ({seconds_elapsed}s decorridos na vela). Strike :00 Chainlink nao foi amostrado no inicio.")
                strike_captured_late = True
            strike = get_chainlink_price()
            if not strike or strike <= 0:
                strike = get_candle_open(window_ts)
            if not strike or strike <= 0:
                print(f"    [🚨 FALHA CRÍTICA DE ORÁCULO]: Impossível capturar Strike aos :00 (Chainlink/Binance indisponíveis). Abortando janela {window_ts} para proteger capital.")
                self.traded_windows.add(window_ts)
                return
            self.candle_strikes[window_ts] = strike

        if window_ts in self.binance_opens:
            binance_open = self.binance_opens[window_ts]
        else:
            binance_open = get_candle_open(window_ts) or get_binance_spot() or strike
            if binance_open:
                self.binance_opens[window_ts] = binance_open

        binance_spot = get_binance_spot() or binance_open
        feed_diff = binance_spot - strike if strike else 0.0
        print(f"    Strike Oraculo Chainlink (K): ${strike:,.2f} | Binance Ref: ${binance_spot:,.2f} (Spread: ${feed_diff:+.2f})")

        # 4. Inicializa Rastreador de TWAP e Amostragem Ativa Contínua até os 135s
        twap_tracker = CandleTWAPTracker(window_ts, strike, symbol="BTCUSDT")
        twap_tracker.backfill_from_binance(time.time())

        eval_sec = 135
        now_sec = int(time.time()) - window_ts
        if now_sec < eval_sec:
            print(f"    Iniciando amostragem contínua de TWAP... aguardando até {eval_sec}s")
            while True:
                now_sec = int(time.time()) - window_ts
                if now_sec >= eval_sec:
                    break
                s_price = get_chainlink_price() or get_binance_spot()
                if s_price:
                    twap_tracker.add_sample(s_price)
                time.sleep(2.0)

        # 5. Analise de Drift e Sinal via Oraculo Chainlink (Spot + TWAP)
        spot_eval = get_chainlink_price()
        if not spot_eval or spot_eval <= 0:
            spot_eval = get_binance_spot()
        if not spot_eval or spot_eval <= 0:
            print(f"    [🚨 FALHA CRÍTICA DE ORÁCULO]: Impossível capturar Spot aos 135s. Abortando janela {window_ts} para proteger capital.")
            self.traded_windows.add(window_ts)
            return

        twap_tracker.add_sample(spot_eval)
        delta = spot_eval - strike
        twap_eval = twap_tracker.get_current_twap()
        twap_delta = twap_tracker.get_twap_delta()
        binance_eval = get_binance_spot() or spot_eval
        spread_eval = binance_eval - spot_eval
        binance_drift = binance_eval - binance_open
        print(f"    Spot Chainlink aos 135s: ${spot_eval:,.2f} | Drift Spot (Delta): ${delta:+.2f}")
        print(f"    TWAP Acumulado aos 135s: ${twap_eval:,.2f} | Drift TWAP: ${twap_delta:+.2f}")
        print(f"    Binance Spot Ref: ${binance_eval:,.2f} | Drift Binance: ${binance_drift:+.2f} | Spread: ${spread_eval:+.2f}")

        # Busca mercado da Polymarket
        market = get_polymarket_market(window_ts)
        if not market:
            print(f"    [Aviso] Mercado da Polymarket para este ciclo ainda nao indexado. Pulando rodada.")
            time.sleep(30)
            return

        try:
            tokens = json.loads(market.get("clobTokenIds", "[]"))
            prices = [float(p) for p in json.loads(market.get("outcomePrices", "[]"))]
            token_up, token_down = tokens[0], tokens[1]
            price_up, price_down = prices[0], prices[1]
        except Exception as e:
            print(f"    [Erro ao processar tokens da Polymarket]: {e}")
            time.sleep(20)
            return

        # Estrategia Quantitativa Sniper Purista (Audit Holdout WR 74.4% | Breakeven 57.9%)
        # DDD e Streak Snapper desativados para nao forcar entradas em ruido (WR marginal 64%)
        target_side = "UP"
        target_token = token_up
        estimated_price = price_up
        rationale = ""
        should_trade_primary = False
        is_streak_snapper = False

        # Deadband dinâmico scale-invariant modulado por Regime Diurno (Dukascopy/HistData + JEV)
        dynamic_deadband, diurnal_regime = get_dynamic_deadband_gate(
            strike, base_bps=DEADBAND_BPS, min_floor=DEADBAND_MIN_FLOOR
        )
        deadband_threshold = dynamic_deadband

        if delta >= dynamic_deadband:
            target_side = "UP"
            target_token = token_up
            estimated_price = price_up
            rationale = f"Drift Positivo Chainlink (+${delta:.1f} >= +${dynamic_deadband:.1f} [{diurnal_regime.get('regime')} {diurnal_regime.get('deadband_multiplier')}x] acima do strike)"
            should_trade_primary = True
        elif delta <= -dynamic_deadband:
            target_side = "DOWN"
            target_token = token_down
            estimated_price = price_down
            rationale = f"Drift Negativo Chainlink (-${abs(delta):.1f} <= -${dynamic_deadband:.1f} [{diurnal_regime.get('regime')} {diurnal_regime.get('deadband_multiplier')}x] abaixo do strike)"
            should_trade_primary = True
        else:
            # REGRA 1 (Deadband): Ruido (|Delta| < dynamic_deadband). Nao forcar aposta primaria no meio do caminho!
            print(f"\n    [🛡️ FILTRO DE RUIDO DEADBAND DINÂMICO]: Delta de ${delta:+.2f} está dentro da zona morta (< ${dynamic_deadband:.2f} | Regime: {diurnal_regime.get('regime')} {diurnal_regime.get('deadband_multiplier')}x).")
            print("       -> Preservando capital! Nenhuma aposta primária forçada no ruído.")
            should_trade_primary = False

        # REGRA DE CONVERGÊNCIA OBRIGATÓRIA (Binance + Chainlink)
        if should_trade_primary:
            if target_side == "UP":
                if binance_drift < -5.0:
                    print(f"\n    [🛡️ FILTRO DE CONVERGENCIA BINANCE]: Divergencia detectada!")
                    print(f"       Chainlink indica UP ({delta:+.2f}), mas Binance indica DOWN ({binance_drift:+.2f})!")
                    print("       -> Preservando capital! Aposta cancelada para nao operar contra a lideranca da Binance.")
                    should_trade_primary = False
            elif target_side == "DOWN":
                if binance_drift > 5.0:
                    print(f"\n    [🛡️ FILTRO DE CONVERGENCIA BINANCE]: Divergencia detectada!")
                    print(f"       Chainlink indica DOWN ({delta:+.2f}), mas Binance indica UP ({binance_drift:+.2f})!")
                    print("       -> Preservando capital! Aposta cancelada para nao operar contra a lideranca da Binance.")
                    should_trade_primary = False

        # REGRA DE CONVERGÊNCIA DE TWAP (Filtro contra Armadilha de Spike / Falso Breakout)
        if should_trade_primary:
            if target_side == "UP":
                if twap_delta < -2.0:
                    print(f"\n    [🛡️ FILTRO DE TWAP ORACLE]: Divergência Crítica detectada!")
                    print(f"       Spot indica UP ({delta:+.2f}), mas TWAP Acumulado está DOWN ({twap_delta:+.2f})!")
                    print("       -> Preservando capital! Aposta cancelada para não cair na armadilha de liquidação do oráculo TWAP.")
                    should_trade_primary = False
            elif target_side == "DOWN":
                if twap_delta > 2.0:
                    print(f"\n    [🛡️ FILTRO DE TWAP ORACLE]: Divergência Crítica detectada!")
                    print(f"       Spot indica DOWN ({delta:+.2f}), mas TWAP Acumulado está UP ({twap_delta:+.2f})!")
                    print("       -> Preservando capital! Aposta cancelada para não cair na armadilha de liquidação do oráculo TWAP.")
                    should_trade_primary = False

        # REGRA DE DISCREPÂNCIA DE ORÁCULO LEAD-LAG (Auditoria JEV: 100% Convicção BPS Dinâmico)
        if should_trade_primary:
            initial_spread = abs(binance_open - strike) if (binance_open and strike) else abs(feed_diff)
            eval_spread = abs(spread_eval)
            max_discrepancy = max(MAX_ORACLE_STRIKE_DISCREPANCY_FLOOR_USD, round(strike * MAX_ORACLE_STRIKE_DISCREPANCY_BPS, 2))
            if initial_spread > max_discrepancy or eval_spread > max_discrepancy:
                print(f"\n    [🛡️ VETO DISCREPÂNCIA DE ORÁCULO LEAD-LAG]:")
                print(f"       Spread Binance vs Chainlink na Abertura: ${initial_spread:.2f} | Aos 135s: ${eval_spread:.2f} (Máx Tolerado: ${max_discrepancy:.2f})")
                print(f"       -> Defasagem crítica de oráculo detectada! Strike viciado por lag de feed. Preservando capital contra convergência tóxica.")
                should_trade_primary = False

        if strike_captured_late and should_trade_primary:
            print(f"\n    [🛡️ FILTRO TEMPO]: Strike K amostrado com atraso (>20s). Entrada primaria cancelada para evitar delta contaminado.")
            should_trade_primary = False

        if should_trade_primary and self._is_past_deadline(window_ts, 295):
            print(f"\n    [🛡️ FILTRO DEADLINE]: Tempo decorrido (>295s) proximo ao fechamento. Entrada primaria abortada.")
            should_trade_primary = False

        # REGRA DE PROTEÇÃO CONTRA CONTRATENDÊNCIA DOW REGIME (Charles Dow & Raghee Horner / JEV AI - Fail-Safe Blindado)
        if should_trade_primary:
            try:
                dow_ok, dow_msg, dow_info = check_dow_counter_trend_veto(
                    target_side=target_side,
                    symbol="BTCUSDT",
                    min_slope_bps=8.0,
                    deadband_delta=delta,
                    strong_reversal_threshold=2.0 * deadband_threshold
                )
                if not dow_ok:
                    print(f"\n    [🛡️ VETO DOW REGIME - JEV]: {dow_msg}")
                    print(f"       -> Preservando capital! Operação contra a tendência macro de Charles Dow (Slope: {dow_info.get('dow_slope_bps', 0.0):+.1f} bps).")
                    should_trade_primary = False
                else:
                    print(f"    [📈 DOW REGIME SHIELD]: {dow_msg}")
            except Exception as e:
                print(f"    [🛡️ FAIL-SAFE GATE - DOW REGIME]: Exceção secundária capturada com segurança ({e}). Prosseguindo com trade primário.")

        # 6. Execucao da Ordem Real Primaria (se aprovada pelos filtros)
        has_primary = False
        primary_stake = FIXED_STAKE
        sold_early = False
        early_sell_tx_hash = ""
        early_sell_price = 0.0
        early_sell_payout = 0.0
        shares = 0.0
        order_id = "SKIPPED"
        tx_hash = ""
        entry_delta = delta

        if should_trade_primary:
            # 6.1 MICROESTRUTURA CLOB: Spread, Imbalance e Microprice (PolyResearch Robotics)
            ob_metrics = get_clob_orderbook(target_token)
            if ob_metrics:
                best_bid = ob_metrics["best_bid"]
                best_ask = ob_metrics["best_ask"]
                spread = ob_metrics["spread"]
                microprice = ob_metrics["microprice"]
                top_imb = ob_metrics["top_imbalance"]
                depth_imb = ob_metrics["depth_imbalance"]

                print(f"\n    [📊 MICROESTRUTURA CLOB - PolyResearch Robotics]:")
                print(f"       Best Bid: ${best_bid:.2f} ({ob_metrics['top_bid_size']:.1f} cotas) | Best Ask: ${best_ask:.2f} ({ob_metrics['top_ask_size']:.1f} cotas)")
                print(f"       Spread: ${spread:.3f} | Microprice: ${microprice:.4f} | Imbalance L1: {top_imb:+.2f} | Depth Imb: {depth_imb:+.2f}")

                # REFINAMENTO DE SPREAD CLOB (Exemplo 12 Wiley 2025 / Aval JEV 90%)
                spread_ok, spread_msg, spread_info = validate_clob_spread_gate(
                    spread=spread,
                    best_bid=best_bid,
                    best_ask=best_ask,
                    top_ask_size=ob_metrics.get("top_ask_size", 0.0),
                    target_stake_usd=FIXED_STAKE,
                    max_tolerable_spread=0.050,
                    optimal_spread_ceiling=0.035,
                    delay_tolerable_spread=0.065
                )

                if spread_info.get("action") == "DELAY_RETRY":
                    print(f"       [⏳ TIMING DE SPREAD (Wiley 2025 Ex. 12)]: {spread_msg}")
                    print(f"       -> Spread entre 5¢ e 6.5¢. Aguardando 2.0s para recomposição do livro L2...")
                    time.sleep(2.0)
                    fresh_ob = get_clob_orderbook(target_token)
                    if fresh_ob:
                        ob_metrics = fresh_ob
                        spread = fresh_ob["spread"]
                        best_bid = fresh_ob["best_bid"]
                        best_ask = fresh_ob["best_ask"]
                        microprice = fresh_ob["microprice"]
                        top_imb = fresh_ob["top_imbalance"]
                        depth_imb = fresh_ob["depth_imbalance"]
                        spread_ok, spread_msg, spread_info = validate_clob_spread_gate(
                            spread=spread, best_bid=best_bid, best_ask=best_ask,
                            top_ask_size=fresh_ob.get("top_ask_size", 0.0),
                            target_stake_usd=FIXED_STAKE,
                            max_tolerable_spread=0.055
                        )
                        if spread_ok:
                            print(f"       [✅ LIQUIDEZ RECOMPOSTA]: Spread apertou para ${spread:.3f}! Entrada autorizada.")
                        else:
                            print(f"       [🛡️ VETO APÓS TOLERÂNCIA]: {spread_msg}. Entrada abortada para evitar slippage.")
                            should_trade_primary = False
                    else:
                        should_trade_primary = False
                elif not spread_ok:
                    print(f"       [🛡️ FILTRO DE SPREAD CLOB]: {spread_msg}")
                    print("       -> Preservando capital! Entrada cancelada devido ao risco de slippage tóxico.")
                    should_trade_primary = False
                else:
                    print(f"       [✅ SPREAD CLOB APROVADO]: {spread_msg} (Regime: {spread_info['regime']})")

                # MELHORIA 2: Filtro de Desbalanceamento do Order Book (Ask Wall Confirmation)
                if should_trade_primary:
                    if top_imb < -0.25 and depth_imb < -0.20:
                        print(f"       [🛡️ FILTRO DE IMBALANCE CLOB]: Desbalanceamento desfavorável (L1: {top_imb:+.2f}, Depth: {depth_imb:+.2f}).")
                        print("       -> Preservando capital! Muralha de venda institucional (Ask Wall) detectada. Entrada cancelada.")
                        should_trade_primary = False
                    else:
                        # MELHORIA 3: Execucao com Microprice Ponderado por Volume
                        if 0.01 <= microprice <= 0.99:
                            estimated_price = round(microprice, 2)
                            print(f"       -> Microprice Ponderado adotado para execução: ${estimated_price:.2f}")
            else:
                # REGRA NO BOOK, NO TRADE (Audit 2.8): Sem Order Book L2 confirmado, nao opera
                print(f"\n    [🛡️ NO BOOK, NO TRADE (Audit 2.8)]: Impossível obter Order Book L2 via CLOB.")
                print("       -> Preservando capital! Entrada primária cancelada por ausência de profundidade confirmada.")
                should_trade_primary = False

        # Continuação dos filtros de risco...
        if should_trade_primary:
            # ── JEV MICROSTRUCTURE GATE (MODO LIVE ATIVO) ───────────────────
            oracle_disc = abs((binance_eval or spot_eval) - spot_eval)
            clob_sp = ob_metrics["spread"] if ob_metrics else 0.04
            obi_val = ob_metrics.get("top_imbalance", 0.0) if ob_metrics else 0.0
            jev_eval = jev_gate.evaluate_entry(
                desk_id="desk1",
                delta_usd=delta,
                binance_drift=binance_drift,
                clob_spread=clob_sp,
                contract_price=estimated_price,
                oracle_discrepancy=oracle_disc,
                seconds_left=max(0, 300 - now_sec),
                obi=obi_val,
                cvd=0.0,
                deadband_threshold=deadband_threshold,
                side=target_side,
                symbol="BTC"
            )
            # JEV ADVISORY MODE: avalia e loga o regime, mas nunca bloca a trade.
            # Para activar VETO real: defina JEV_LIVE_GATE=true no .env
            jev_verdict = jev_eval.get("verdict", "APPROVE_BYPASS")
            jev_regime  = jev_eval.get("candle_regime", "?")
            jev_score   = jev_eval.get("would_veto", 0.0)
            jev_ms      = jev_eval.get("elapsed_ms", 0)
            if jev_verdict == "VETO":
                print(f"\n    [🧠 JEV ADVISORY - VETO OBSERVADO]: {jev_eval.get('veto_reason')}")
                print(f"       -> Regime: {jev_regime} | Score: {jev_score} | {jev_ms}ms | (MODO ADVISORY: trade continua)")
            else:
                print(f"    [🧠 JEV ADVISORY]: Regime: {jev_regime} | Score: {jev_score} | Veredito: {jev_verdict} ({jev_ms}ms)")

            # Consulta preco real de execucao no livro CLOB se ainda elegivel
            if should_trade_primary:
                try:
                    real_book_price = self.client.calculate_market_price(target_token, "BUY", FIXED_STAKE, OrderType.FAK)
                    if real_book_price and real_book_price > 0:
                        estimated_price = real_book_price
                except Exception:
                    pass

            # REGRA 2: Filtro de Faixa de Preco Sniper Purista ($0.35 a $0.62)
            if should_trade_primary:
                if estimated_price < PRIMARY_MIN_PRICE:
                    print(f"    [🛡️ FILTRO DE PRECO]: Preco ${estimated_price:.2f} < ${PRIMARY_MIN_PRICE:.2f} (Penny Trap). Pulando entrada primaria.")
                    should_trade_primary = False
                elif estimated_price > PRIMARY_MAX_PRICE:
                    print(f"    [🛡️ FILTRO DE PRECO SNIPER]: Preco ${estimated_price:.2f} > ${PRIMARY_MAX_PRICE:.2f} (Breakeven desfavoravel > 55%). Pulando entrada primaria.")
                    should_trade_primary = False

            # REGRA 3: Filtro de Liquidações Binance Futures (Order Flow Convicção / Anti-Trap)
            if should_trade_primary:
                liq_stats = self.liq_watcher.get_window_liquidations(window_seconds=135)
                print(f"\n    [🌊 FLUXO DE LIQUIDAÇÕES BINANCE]:")
                print(f"       Longs: ${liq_stats['long_vol_usd']:,.0f} | Shorts: ${liq_stats['short_vol_usd']:,.0f} | Sinal: {liq_stats['dominant_signal']}")
                if liq_stats["dominant_signal"] != "NEUTRAL":
                    if liq_stats["dominant_signal"] != target_side:
                        print(f"       [⚠️ ALERTA DE DIVERGÊNCIA]: Sinal de Liquidação ({liq_stats['dominant_signal']}) contradiz direção técnica ({target_side}).")
                        print("       -> Preservando capital! Abortando entrada para evitar armadilha de touro/urso.")
                        should_trade_primary = False
                    else:
                        print(f"       [🔥 ALTA CONVICÇÃO]: Cascata de Liquidação confirmando {target_side} (${liq_stats['total_vol_usd']:,.0f} liquidado)!")
                        rationale += f" + Confirmação de Liquidação ({liq_stats['dominant_signal']})"

            # REGRA 4: Filtro de CVD / OFI Tick Data (Anti-Armadilha de Absorção Institucional e Taker Divergence)
            if should_trade_primary and not is_streak_snapper:
                cvd_stats = self.cvd_watcher.get_window_cvd(window_seconds=135)
                net_cvd_usd = cvd_stats["net_cvd_usd"]
                net_cvd_btc = net_cvd_usd / max(1.0, spot_eval)
                bookticker_info = self.cvd_watcher.get_order_book_imbalance(lookback_sec=3.0)
                rolling_obi = bookticker_info.get("rolling_obi", 0.0)

                print(f"\n    [🌊 FLUXO DE CVD / OFI & BOOKTICKER (100 GB TICK & BOOK ALPHA)]:")
                print(f"       Net CVD: ${net_cvd_usd/1e6:+.2f}M ({net_cvd_btc:+.2f} BTC) | Ratio Compra: {cvd_stats['cvd_ratio']*100:.1f}% | Sinal: {cvd_stats['dominant_signal']} ({cvd_stats['source']})")
                print(f"       Top-of-Book OBI: {rolling_obi:+.3f} ({bookticker_info.get('obi_direction', 'NEUTRAL')}) | Spread: ${bookticker_info.get('spread_usd', 0):.2f}")

                # Gate Institucional de Microestrutura JEV (CVD + BookTicker OBI Anti-Absorção)
                ofi_ok, ofi_msg = check_order_flow_imbalance_gate(
                    target_side=target_side,
                    dominant_signal=cvd_stats["dominant_signal"],
                    net_cvd_usd=net_cvd_usd,
                    cvd_ratio=cvd_stats["cvd_ratio"],
                    bookticker_obi=rolling_obi
                )

                if not ofi_ok:
                    print(f"       [🛡️ FILTRO OFI / ABSORÇÃO PASSIVA VETO (JEV)]: {ofi_msg}")
                    print("       -> Preservando capital! Abortando entrada primária para evitar armadilha de liquidez de baleia.")
                    should_trade_primary = False
                elif cvd_stats["dominant_signal"] == target_side:
                    print(f"       [🔥 ALTA CONVICÇÃO CVD/OFI]: Fluxo institucional 100% alinhado com {target_side} ({net_cvd_btc:+.1f} BTC)!")
                    rationale += f" + Convicção CVD/OFI ({cvd_stats['dominant_signal']}, {net_cvd_btc:+.1f} BTC)"

                # REGRA 4.1: Detector de Velocidade e Aceleração Lead-Lag (Polymarket 2025 Bot Model)
                if should_trade_primary:
                    velo_data = self.cvd_watcher.get_velocity_lead_lag(window_seconds=3.0, min_velocity_threshold=12.0)
                    v_usd_s = velo_data.get("velocity_usd_sec", 0.0)
                    v_disp = velo_data.get("price_displacement", 0.0)
                    v_dir = velo_data.get("direction", "NEUTRAL")

                    if velo_data.get("is_high_velocity", False):
                        if (target_side == "UP" and v_dir == "DOWN") or (target_side == "DOWN" and v_dir == "UP"):
                            print(f"       [🛡️ VETO VELOCIDADE ADVERSA (SPEED GAP LEAD-LAG)]: Binance acelerando contra {target_side} ({v_usd_s:+.1f} $/s, deslocamento: ${v_disp:+.1f})!")
                            print("       -> Preservando capital! Abortando entrada para não ser atropelado pela Binance no fechamento da janela de 2.7s.")
                            should_trade_primary = False
                        elif (target_side == "UP" and v_dir == "UP") or (target_side == "DOWN" and v_dir == "DOWN"):
                            print(f"       [⚡ ALTA CONVICÇÃO LEAD-LAG]: Binance acelerando forte a favor de {target_side} ({v_usd_s:+.1f} $/s, deslocamento: ${v_disp:+.1f})!")
                            rationale += f" + Speed Lead-Lag ({v_usd_s:+.1f} $/s, ${v_disp:+.1f})"

                # Gate de Amplitude e Toxic Flow de Altcoins (JEV Lote 3 - Anti-Fakeout)
                if should_trade_primary:
                    try:
                        alt_deltas = {}
                        sol_st = safe_read_json(os.path.join(BASE_DIR, "sol_live_market_state.json"), {})
                        if sol_st and sol_st.get("strike") and sol_st.get("spot"):
                            alt_deltas["SOL"] = (float(sol_st["spot"]) - float(sol_st["strike"])) / float(sol_st["strike"])
                        eth_st = safe_read_json(os.path.join(BASE_DIR, "eth_live_market_state.json"), {})
                        if eth_st and eth_st.get("strike") and eth_st.get("spot"):
                            alt_deltas["ETH"] = (float(eth_st["spot"]) - float(eth_st["strike"])) / float(eth_st["strike"])

                        alt_ok, alt_msg = check_altcoin_market_breadth_gate(target_side=target_side, altcoin_deltas=alt_deltas)
                        if not alt_ok:
                            print(f"       [🛡️ FILTRO BREADTH ALTCOINS VETO (JEV Lote 3)]: {alt_msg}")
                            print("       -> Preservando capital! Abortando entrada: Bitcoin diverge do fluxo geral de altcoins.")
                            should_trade_primary = False
                        else:
                            print(f"       [✅ BREADTH ALTCOINS]: Fluxo cruzado SOL/ETH sem divergências críticas contra {target_side}.")
                    except Exception:
                        pass

                # Gate de Viés de Sessão Asiática (CacheCarti Alpha / 7-Stage Validated)
                if should_trade_primary:
                    try:
                        cur_hour = datetime.now(timezone.utc).hour if "timezone" in globals() else None
                        asia_ok, asia_msg, asia_info = check_asia_session_drift_gate(target_side=target_side, current_utc_hour=cur_hour)
                        if not asia_ok:
                            print(f"       [🛡️ FILTRO ASIA DRIFT BIAS VETO (CacheCarti Alpha)]: {asia_msg}")
                            print("       -> Preservando capital! Abortando entrada: Sinal contra a tendência estrutural da sessão asiática.")
                            should_trade_primary = False
                        elif asia_info.get("is_us_session") and abs(asia_info.get("asia_drift_bps", 0.0)) >= 25.0:
                            print(f"       [🔥 ALTA CONVICÇÃO ASIA-US FLOW]: Trade {target_side} alinhado com drift asiático ({asia_info['asia_drift_bps']:+.1f} bps)!")
                            rationale += f" + Alinhamento Ásia ({asia_info['asia_drift_bps']:+.1f} bps)"
                    except Exception:
                        pass

        if should_trade_primary:
            # 6.2 PRICING INSTITUCIONAL: Black-Scholes + Atualização Bayesiana (Anti-Colinearidade)
            sec_left = max(1, 300 - int(time.time() - window_ts))
            eff_vol = 0.32
            tau = max(1.0, float(sec_left)) / (365.25 * 24 * 3600)
            sig_sqrt_tau = eff_vol * math.sqrt(tau)
            d2 = (math.log(max(1.0, spot_eval) / max(1.0, strike)) - 0.5 * (eff_vol ** 2) * tau) / max(1e-9, sig_sqrt_tau)
            bs_prob_up = 0.5 * (1.0 + math.erf(d2 / math.sqrt(2.0)))
            bs_fair = bs_prob_up if target_side == "UP" else (1.0 - bs_prob_up)

            # Sinal de microestrutura para evidência Bayesiana (OBI e Microprice)
            p_sig = 0.65 if (ob_metrics and ob_metrics["top_imbalance"] > 0.1) else (0.35 if (ob_metrics and ob_metrics["top_imbalance"] < -0.1) else 0.50)
            model_fair_value = bayesian_fair_value(
                prior_prob=bs_fair,
                p_signal_if_outcome=p_sig if target_side == "UP" else (1.0 - p_sig),
                p_signal_if_alternative=0.50,
                collinearity_discount=0.75
            )

            # 6.3 DIMENSIONAMENTO DINÂMICO POR KELLY FRACIONÁRIO (Blindado contra Overbetting)
            real_usdc = self.get_usdc_balance() if self.execution_mode != "paper" else 50.0
            cur_bankroll = max(10.0, real_usdc)
            min_stake_val = 1.00
            # Teto estrito: máximo de 8% da carteira real ou $2.50 (o que for menor), garantindo aposta segura entre $1.00 e $2.50
            max_stake_val = min(2.50, max(1.00, round(cur_bankroll * 0.08, 2)))
            target_stake, kelly_status = compute_dynamic_stake(
                bankroll=cur_bankroll,
                win_probability=model_fair_value,
                entry_price=estimated_price,
                fallback_stake=FIXED_STAKE,
                kelly_fraction=0.25,
                min_stake=min_stake_val,
                max_stake=max_stake_val
            )

            if target_stake <= 0.0:
                print(f"    [🛡️ VETO KELLY FRACIONÁRIO]: {kelly_status}. Edge líquido insuficiente para justificar exposição.")
                should_trade_primary = False
            else:
                # 6.4 PROFUNDIDADE REAL DO LIVRO (VWAP L2) E VALIDAÇÃO DE NET EDGE EXECUTÁVEL
                asks_raw = ob_metrics.get("asks_raw", []) if ob_metrics else []
                vwap_price, vwap_cost, vwap_shares, slip_bps = calculate_vwap_ask(asks_raw, target_usd=target_stake)

                if vwap_price is None:
                    print(f"    [🛡️ FILTRO DE PROFUNDIDADE VWAP]: Livro L2 raso! Liquidez disponível (${vwap_cost:.2f}) insuficiente para absorver ordem de ${target_stake:.2f}.")
                    should_trade_primary = False
                else:
                    # Checagem centralizada no RiskGate (Fail-Closed)
                    gate_ok, gate_msg = check_pre_trade_gate(
                        desk_id="DESK1_BTC_5M",
                        target_side=target_side,
                        stake=target_stake,
                        spot_price=spot_eval,
                        strike_price=strike,
                        oracle_timestamp=time.time(),
                        current_balance=cur_bankroll,
                        execution_mode=self.execution_mode,
                        fair_value=model_fair_value,
                        vwap_price=vwap_price,
                        min_net_edge=0.015
                    )
                    if not gate_ok:
                        print(f"    [🛡️ RISK GATE VETO]: {gate_msg}")
                        should_trade_primary = False
                    else:
                        estimated_price = vwap_price
                        primary_stake = target_stake
                        print(f"    [💎 EXECUÇÃO APROVADA - VWAP + KELLY]:")
                        print(f"       Fair Value Bayesiano: {model_fair_value:.2%} | VWAP Fill: ${vwap_price:.4f} (Slippage: {slip_bps:.1f} bps)")
                        print(f"       Stake Kelly (25%): ${target_stake:.2f} ({kelly_status}) | Cotas Estimadas: {vwap_shares:.2f}")

        if should_trade_primary:
            print(f"\n    [ENTRADA QUANTITATIVA]: {target_side} | Preco Real (Microprice/VWAP): ${estimated_price:.4f}")
            print(f"       Racional: {rationale}")

            # ── CROSS-VENUE SYNPATH FOMO TAKER FLOW GATE (BTC DUAL-VENUE INTELLIGENCE) ──
            # Validado no Backtest de 164 operações do Desk 1:
            # Elimina exaustão institucional extrema (> +0.80 & Vol >= 10k) com ZERO vitórias sacrificadas
            try:
                from zoneinfo import ZoneInfo
                end_s = ((int(time.time()) // 900) + 1) * 900
                end_u = datetime.fromtimestamp(end_s, tz=timezone.utc)
                end_ny = end_u.astimezone(ZoneInfo("America/New_York"))
                k_ticker = f"KXBTC15M-{end_ny.strftime('%y')}{end_ny.strftime('%b').upper()}{end_ny.strftime('%d')}{end_ny.strftime('%H')}{end_ny.strftime('%M')}-{end_ny.strftime('%M')}"
                k_side = "YES" if target_side == "UP" else "NO"

                fomo_ok, fomo_msg, fomo_data = check_kalshi_synpath_fomo_gate(
                    ticker=k_ticker,
                    target_side=k_side,
                    threshold=0.80,
                    min_volume=10000.0,
                    window_sec=60
                )
                if not fomo_ok:
                    print(f"       [🛑 VETO CROSS-VENUE SYNPATH ANTI-FOMO]: {fomo_msg}")
                    print(f"          -> Kalshi {k_ticker}: Imbalance {fomo_data.get('imbalance', 0):+.2f} | Volume: {fomo_data.get('total_vol', 0):,.0f} contratos.")
                    print(f"          -> Varejo em euforia extrema na Kalshi. Abortando entrada no Polymarket para proteger capital!")
                    should_trade_primary = False
                else:
                    print(f"       [📊 CROSS-VENUE SYNPATH FLOW]: {fomo_msg} (Kalshi {k_ticker})")
            except Exception as e:
                print(f"       [Aviso Cross-Venue Synpath Gate]: {e}")

            maker_entry_attempted = False
            best_bid_clob = ob_metrics["best_bid"] if ob_metrics else 0.0
            best_ask_clob = ob_metrics["best_ask"] if ob_metrics else 0.0

            # Estratégia Maker Post-Only Inteligente (Touch Quoting JEV):
            # Se o spread permitir (>= 0.02) e o preço touch estiver dentro da margem, posta 1 tick dentro do touch
            if ob_metrics and spread >= 0.02 and best_bid_clob > 0 and (best_bid_clob + 0.01) <= PRIMARY_MAX_PRICE:
                touch_price = round(best_bid_clob + 0.01, 2)
                print(f"       [🎯 MAKER POST-ONLY JEV]: Cotando 1 tick dentro do spread a ${touch_price:.2f} (Best Bid: ${best_bid_clob:.2f} | Best Ask: ${best_ask_clob:.2f})...")
                post_res = self.place_live_order(target_token, "BUY", primary_stake, price=touch_price, max_price=PRIMARY_MAX_PRICE, post_only=True)
                if post_res.get("status") == "SUCCESS":
                    maker_order_id = post_res.get("response", {}).get("orderID", "")
                    print(f"       -> Ordem Post-Only enviada com sucesso (ID: {maker_order_id})! Aguardando fill passivo...")
                    maker_entry_attempted = True
                    for _mk_chk in range(5):  # Monitora por até 10 segundos
                        time.sleep(2.0)
                        mk_bal = self.get_token_balance(target_token) if self.execution_mode != "paper" else (primary_stake / touch_price)
                        if mk_bal and mk_bal >= 0.5:
                            order_res = post_res
                            estimated_price = touch_price
                            print(f"       🎉 [MAKER FILL CONCLUÍDO]: Ordem preenchida passivamente a ${touch_price:.2f}! Spread capturado com sucesso.")
                            break
                    if not (mk_bal and mk_bal >= 0.5) and self.execution_mode != "paper":
                        print(f"       [⏳ MAKER TIMEOUT]: Ordem Post-Only não preenchida em 10s. Cancelando ordem resting para evitar slippage tardio...")
                        try:
                            if maker_order_id:
                                self.client.cancel_order(maker_order_id)
                        except Exception:
                            pass
                        maker_entry_attempted = False

            if not maker_entry_attempted:
                limit_p = min(PRIMARY_MAX_PRICE, round(estimated_price + 0.01, 2))
                order_res = self.place_live_order(target_token, "BUY", primary_stake, price=limit_p, max_price=PRIMARY_MAX_PRICE, post_only=False)
                print(f"       Resultado do Envio Primário: {order_res.get('status')}")

            if order_res.get("status") == "SUCCESS":
                resp_data = order_res.get("response", {})
                order_id = resp_data.get("orderID") or "EXECUTED"
                tx_hashes = resp_data.get("transactionsHashes") or []
                tx_hash = tx_hashes[0] if tx_hashes else ""

                if self.execution_mode == "paper":
                    has_primary = True
                    shares = round(primary_stake / max(0.01, estimated_price), 4)
                    print(f"       -> [MODO PAPER] ORDEM PRIMÁRIA SIMULADA! ID: {order_id} | {shares:.4f} cotas @ ${estimated_price:.4f}")
                else:
                    real_tok_bal = 0.0
                    for _attempt in range(6):
                        time.sleep(1.5)
                        real_tok_bal = self.get_token_balance(target_token)
                        if real_tok_bal > 0:
                            break
                    if real_tok_bal == 0 and order_id and order_id != "EXECUTED":
                        try:
                            ord_info = self.client.get_order(order_id)
                            if ord_info and float(ord_info.get("size_matched", 0)) > 0:
                                real_tok_bal = float(ord_info.get("size_matched", 0))
                        except Exception:
                            pass
                    if real_tok_bal > 0:
                        has_primary = True
                        shares = real_tok_bal
                        print(f"       -> ORDEM PRIMÁRIA EXECUTADA! ID: {order_id} | Tx: {tx_hash} | {shares:.4f} cotas reais confirmadas")
                    else:
                        has_primary = False
                        order_id = "UNFILLED"
                        tx_hash = ""
                        print(f"       [AVISO EXECUÇÃO] Ordem enviada mas sem liquidez no limite (${limit_p:.2f}). Nenhuma cota recebida (FAK não-preenchido).")
                        print("       -> Entrada primária desconsiderada (evitando registro de posição fantasma).")
            else:
                # Dupla verificação no loop principal contra falha/timeout
                reconciled_bal = 0.0
                if self.execution_mode != "paper":
                    time.sleep(1.0)
                    reconciled_bal = self.get_token_balance(target_token)
                
                if reconciled_bal and reconciled_bal >= 0.5:
                    has_primary = True
                    shares = reconciled_bal
                    order_id = "RECONCILED_ONCHAIN"
                    tx_hash = ""
                    print(f"       [🚨 RECUPERAÇÃO DE ENTRADA]: Resposta indicou falha ({order_res.get('error')}), mas {shares:.4f} cotas foram localizadas na Safe!")
                    print("       -> Posição assumida com sucesso para gestão quantitativa!")
                else:
                    has_primary = False
                    order_id = "FAILED"
                    tx_hash = ""
                    print(f"       [Falha no envio da ordem]: {order_res.get('error')}")
                    print("       -> Entrada primária não realizada. Monitorando oportunidade de Sweeper (BTC5MScour)...")
        else:
            print("       -> Entrada primária dispensada. Monitorando oportunidades defensivas e Sweeper (BTC5MScour)...")

        # 7. Monitoramento Ativo Multi-Addon (140s aos 285s)
        # Add-ons: SirMartingale (Take-Profit >= 0.86), Bonereaper (Hedge Delta <= -18), BTC5MScour (Sweeper 255s-285s)
        hedged = False
        hedge_attempted = False
        hedge_side = "DOWN" if target_side == "UP" else "UP"
        hedge_token = token_down if target_side == "UP" else token_up
        hedge_order_id = ""
        hedge_tx_hash = ""
        hedge_shares = 0.0
        hedge_price = price_down if target_side == "UP" else price_up
        payout_hedge = 0.0

        scour_executed = False
        scour_attempted = False
        scour_side = ""
        scour_token = ""
        scour_order_id = ""
        scour_tx_hash = ""
        scour_shares = 0.0
        scour_price = 0.0
        payout_scour = 0.0
        last_candle_chainlink = spot_eval
        monitor_addons = ["SirMartingale (TP >= 0.86)", "Bonereaper (Hedge <= 0.45)", "Stop-Loss"]
        if SCOUR_ENABLED:
            monitor_addons.append("BTC5MScour (Sweeper)")
        print(f"\n    [🎯 SNIPER PURISTA MONITOR]: Monitorando {' | '.join(monitor_addons)}...")
        while True:
            now_loop = int(time.time())
            elapsed = now_loop - window_ts
            if elapsed >= 285:
                break

            current_chainlink = get_chainlink_price() or get_binance_spot()
            if current_chainlink:
                last_candle_chainlink = current_chainlink
                current_delta = current_chainlink - strike
                twap_tracker.add_sample(current_chainlink)
                current_twap = twap_tracker.get_current_twap()
                current_twap_delta = twap_tracker.get_twap_delta()

                # --- ADD-ON 1: SirMartingale (Take-Profit Dinâmico Escalonado) ---
                if has_primary and not sold_early and elapsed >= 165:
                    ob_tp = get_clob_orderbook(target_token)
                    if ob_tp:
                        cur_bid = ob_tp["best_bid"]
                        bid_size = ob_tp["top_bid_size"]
                        # 1. Alvo padrão: 0.86 ou 1.30x entrada
                        min_tp_price = max(TAKE_PROFIT_PRICE_THRESHOLD, round(estimated_price * 1.30, 3))

                        # 2. Se entrada barata (<= $0.52), meta de +40% já garante excelente realização
                        if estimated_price <= 0.52:
                            min_tp_price = min(min_tp_price, max(0.70, round(estimated_price * 1.40, 2)))

                        # 2.1 Refinamento JEV (Staged TP para cotas baratas <= $0.40): Travar lucro expressivo se bid bater >= 68¢ aos 200s+
                        if estimated_price <= 0.40 and elapsed >= 200:
                            min_tp_price = min(min_tp_price, max(0.68, round(estimated_price * 1.75, 2)))

                        # 3. Se tempo avançado (elapsed >= 225s), garante lucro sólido antes dos segundos finais
                        if elapsed >= 225 and cur_bid >= 0.76 and cur_bid >= round(estimated_price * 1.25, 2):
                            min_tp_price = min(min_tp_price, cur_bid)

                        if cur_bid >= min_tp_price and bid_size >= 1.0:
                            print(f"\n    [💰 SIRMARTINGALE TAKE-PROFIT!] Aos {elapsed}s: CLOB Best Bid atingiu ${cur_bid:.2f} (>= ${min_tp_price:.2f}, entrada: ${estimated_price:.2f})!")
                            try:
                                if self.client:
                                    self.client.cancel_all()
                            except Exception:
                                pass
                            real_tok = self.get_token_balance(target_token) if self.execution_mode != "paper" else shares
                            raw_s = real_tok if (real_tok is not None and real_tok >= 0.5) else shares
                            sell_shares = int(raw_s * 100) / 100.0
                            sell_res = None
                            tp_limit_price = max(min_tp_price, round(cur_bid - 0.02, 2))
                            if sell_shares >= 0.1 and not self._is_past_deadline(window_ts, 295):
                                print(f"       Vendendo {sell_shares:.2f} cotas na CLOB para travar lucro (Best Bid: ${cur_bid:.2f} | Limite Aceito: ${tp_limit_price:.2f} | ~+{((cur_bid/max(0.01, estimated_price)-1)*100):.0f}%)...")
                                sell_res = self.place_live_order(target_token, "SELL", sell_shares, price=tp_limit_price)
                            if sell_res and sell_res.get("status") == "SUCCESS":
                                sell_confirmed = True
                                if self.execution_mode != "paper":
                                    time.sleep(1.0)
                                    rem_tok = self.get_token_balance(target_token)
                                    if rem_tok >= sell_shares:
                                        print(f"       [ALERTA TAKE-PROFIT] Ordem aceita pela API mas cotas continuam na carteira ({rem_tok:.2f} cotas). FAK não preenchido.")
                                        sell_confirmed = False

                                if sell_confirmed:
                                    s_resp = sell_res.get("response", {})
                                    s_hashes = s_resp.get("transactionsHashes") or []
                                    early_sell_tx_hash = s_hashes[0] if s_hashes else (s_resp.get("orderID") or "EXECUTED")
                                    resp_tp_price = s_resp.get("price")
                                    actual_tp_price = resp_tp_price if (resp_tp_price is not None and resp_tp_price > 0) else cur_bid
                                    if self.execution_mode != "paper" and self.client:
                                        fill = self.get_latest_clob_fill(target_token, side="SELL", min_timestamp=window_ts)
                                        if fill:
                                            actual_tp_price = fill["price"]
                                            early_sell_tx_hash = fill["tx_hash"] or early_sell_tx_hash
                                    sold_early = True
                                    has_primary = False
                                    early_sell_price = actual_tp_price
                                    early_sell_payout = round(sell_shares * actual_tp_price, 2)
                                    print(f"       -> VENDA ANTECIPADA EXECUTADA! Tx: {early_sell_tx_hash} | Payout Travado: ${early_sell_payout:.2f} USDC (Preço: ${actual_tp_price:.2f})")
                                else:
                                    print("       -> Venda antecipada não consumada no livro. Posição mantida aberta para próxima tentativa.")
                            else:
                                print(f"       [Falha na venda antecipada]: {sell_res.get('error') if sell_res else 'Saldo insuficiente ou deadline excedido'}")

                # --- DEFESA: Bonereaper Hedge Dinamico e Evaporação de Drift ---
                reversal = False
                evaporation = False
                twap_compromised = False
                if has_primary and not sold_early:
                    cur_b_spot = get_binance_spot() or current_chainlink
                    b_open = self.binance_opens.get(window_ts, strike)
                    b_drift = (cur_b_spot - b_open) if (cur_b_spot and b_open) else current_delta
                    
                    # 1. Reversão contra o strike além do ruído do Bitcoin (Escudo Anti-Whipsaw >= 210s)
                    dynamic_rev_thresh, _ = get_dynamic_deadband_gate(strike, base_bps=DEADBAND_BPS, min_floor=20.0)
                    if elapsed >= 210:
                        if target_side == "UP":
                            if (current_delta <= -dynamic_rev_thresh and b_drift <= -10.0) or (current_delta <= -15.0 and b_drift <= -15.0):
                                reversal = True
                        elif target_side == "DOWN":
                            if (current_delta >= dynamic_rev_thresh and b_drift >= 10.0) or (current_delta >= 15.0 and b_drift >= 15.0):
                                reversal = True

                    # 2. Evaporação de Drift: só aciona nos segundos finais (>= 225s) se a margem foi completamente perdida e cruzou contra
                    if not reversal and elapsed >= 225 and abs(entry_delta) >= 25.0:
                        if target_side == "UP" and current_delta <= -10.0 and b_drift <= -8.0:
                            evaporation = True
                        elif target_side == "DOWN" and current_delta >= 10.0 and b_drift >= 8.0:
                            evaporation = True

                    # 3. Comprometimento Matemático de TWAP (>= 195s)
                    # Se o TWAP estiver desfavorável e o preço à vista necessário para virar for inalcançável:
                    if not reversal and not evaporation and elapsed >= 195:
                        if target_side == "UP":
                            req_spot = twap_tracker.get_required_spot_to_win("UP", elapsed)
                            if req_spot and (req_spot - current_chainlink) >= 15.0:
                                twap_compromised = True
                        elif target_side == "DOWN":
                            req_spot = twap_tracker.get_required_spot_to_win("DOWN", elapsed)
                            if req_spot and (current_chainlink - req_spot) >= 15.0:
                                twap_compromised = True

                # Trata evaporação de borda ou comprometimento de TWAP preventivamente via Stop-Loss
                if (evaporation or twap_compromised) and not sold_early and not hedged:
                    alert_desc = "COMPROMETIMENTO DE TWAP ORACLE" if twap_compromised else "EVAPORAÇÃO DE DRIFT"
                    print(f"\n    [⚠️ {alert_desc} DETECTADO!] Aos {elapsed}s:")
                    print(f"       Spot Delta: ${current_delta:+.2f} | TWAP Delta: ${current_twap_delta:+.2f} (contra {target_side}).")
                    
                    # Escudo Anti-Sweep (Ziad Francis SMC): Veta stop-loss se for apenas absorção transitória de liquidez (wick)
                    sweep_check = evaluate_anti_sweep_shield(
                        symbol="BTCUSDT",
                        window_ts=window_ts,
                        elapsed=elapsed,
                        target_side=target_side,
                        strike=strike,
                        current_spot=cur_b_spot,
                        current_delta=current_delta,
                        twap_delta=current_twap_delta
                    )
                    if sweep_check["is_sweep"]:
                        if elapsed % 10 < 3:
                            print(f"    [🛡️ ANTI-SWEEP SHIELD (ZIAD ALGO)]: Veto de Stop-Loss aos {elapsed}s! {sweep_check['reason']}")
                    else:
                        sl_data = self._execute_emergency_stop_loss(target_token, target_side, shares, window_ts)
                        if sl_data["success"]:
                            sold_early = True
                            has_primary = False
                            early_sell_tx_hash = sl_data["tx_hash"]
                            early_sell_price = sl_data["price"]
                            early_sell_payout = sl_data["payout"]

                if reversal and not hedged and not hedge_attempted:
                    hedge_attempted = True
                    print(f"\n    [⚠️ ALERTA DE REVERSAO DETECTADA!] Aos {elapsed}s:")
                    print(f"       Chainlink: ${current_chainlink:,.2f} | Delta: {current_delta:+.2f} (contra {target_side})")

                    # 1. Avalia preco REAL da cota de protecao no livro da CLOB
                    ob_hedge = get_clob_orderbook(hedge_token)
                    hedge_best_ask = ob_hedge["best_ask"] if ob_hedge else 0.0

                    cur_bal = self.get_usdc_balance()
                    if 0.01 <= hedge_best_ask <= HEDGE_MAX_PRICE and cur_bal >= HEDGE_STAKE and not self._is_past_deadline(window_ts, 295):
                        print(f"    [🛡️ BONEREAPER HEDGE ATIVADO]: Livro CLOB com preco favoravel para hedge: ${hedge_best_ask:.2f} (<= ${HEDGE_MAX_PRICE:.2f}).")
                        print(f"       Enviando ordem de protecao de ${HEDGE_STAKE:.2f} USDC em {hedge_side}...")
                        order_limit_p = min(HEDGE_MAX_PRICE, round(hedge_best_ask + 0.01, 2))
                        hedge_res = self.place_live_order(hedge_token, "BUY", HEDGE_STAKE, price=order_limit_p, max_price=HEDGE_MAX_PRICE)
                        if hedge_res.get("status") == "SUCCESS":
                            if self.execution_mode == "paper":
                                hedged = True
                                h_resp = hedge_res.get("response", {})
                                hedge_order_id = h_resp.get("orderID") or "EXECUTED"
                                h_hashes = h_resp.get("transactionsHashes") or []
                                hedge_tx_hash = h_hashes[0] if h_hashes else hedge_order_id
                                hedge_price = hedge_best_ask
                                hedge_shares = round(HEDGE_STAKE / max(0.01, hedge_price), 4)
                                print(f"       -> [MODO PAPER] HEDGE SIMULADO COM SUCESSO! Tx: {hedge_tx_hash} | {hedge_shares} cotas @ ${hedge_price:.2f}")
                            else:
                                real_h_tok = 0.0
                                for _ in range(3):
                                    time.sleep(1.5)
                                    real_h_tok = self.get_token_balance(hedge_token)
                                    if real_h_tok > 0:
                                        break
                                if real_h_tok > 0:
                                    hedged = True
                                    h_resp = hedge_res.get("response", {})
                                    hedge_order_id = h_resp.get("orderID") or "EXECUTED"
                                    h_hashes = h_resp.get("transactionsHashes") or []
                                    hedge_tx_hash = h_hashes[0] if h_hashes else hedge_order_id
                                    hedge_price = hedge_best_ask
                                    hedge_shares = real_h_tok
                                    print(f"       -> HEDGE EXECUTADO COM SUCESSO! Tx: {hedge_tx_hash} | {hedge_shares:.4f} cotas @ ${hedge_price:.2f}")
                                else:
                                    print(f"       [AVISO HEDGE] Ordem enviada mas cota de hedge nao preenchida (FAK). Avaliando Stop-Loss com Anti-Sweep...")
                                    sweep_check = evaluate_anti_sweep_shield(
                                        symbol="BTCUSDT",
                                        window_ts=window_ts,
                                        elapsed=elapsed,
                                        target_side=target_side,
                                        strike=strike,
                                        current_spot=cur_b_spot,
                                        current_delta=current_delta,
                                        twap_delta=current_twap_delta
                                    )
                                    if not sweep_check["is_sweep"]:
                                        sl_data = self._execute_emergency_stop_loss(target_token, target_side, shares, window_ts)
                                        if sl_data["success"]:
                                            sold_early = True
                                            has_primary = False
                                            early_sell_tx_hash = sl_data["tx_hash"]
                                            early_sell_price = sl_data["price"]
                                            early_sell_payout = sl_data["payout"]
                                    else:
                                        print(f"       [🛡️ ANTI-SWEEP SHIELD (ZIAD ALGO)]: Veto de Stop-Loss pós-hedge! {sweep_check['reason']}")
                        else:
                            print(f"       [Falha no hedge]: {hedge_res.get('error')}. Avaliando Stop-Loss com Anti-Sweep...")
                            sweep_check = evaluate_anti_sweep_shield(
                                symbol="BTCUSDT",
                                window_ts=window_ts,
                                elapsed=elapsed,
                                target_side=target_side,
                                strike=strike,
                                current_spot=cur_b_spot,
                                current_delta=current_delta,
                                twap_delta=current_twap_delta
                            )
                            if not sweep_check["is_sweep"]:
                                sl_data = self._execute_emergency_stop_loss(target_token, target_side, shares, window_ts)
                                if sl_data["success"]:
                                    sold_early = True
                                    has_primary = False
                                    early_sell_tx_hash = sl_data["tx_hash"]
                                    early_sell_price = sl_data["price"]
                                    early_sell_payout = sl_data["payout"]
                            else:
                                print(f"       [🛡️ ANTI-SWEEP SHIELD (ZIAD ALGO)]: Veto de Stop-Loss pós-hedge! {sweep_check['reason']}")
                    else:
                        if hedge_best_ask > HEDGE_MAX_PRICE:
                            print(f"    [🛡️ HEDGE RECUSADO - EV NEGATIVO]: Preco de {hedge_side} esta em ${hedge_best_ask:.2f} (> ${HEDGE_MAX_PRICE:.2f}).")
                            print("       Comprar a ponta oposta no topo garante prejuizo certo ($1.00 gasto para < $1.00 retorno).")
                        elif cur_bal < HEDGE_STAKE:
                            print(f"       [Aviso Hedge] Saldo insuficiente (${cur_bal:.2f}) para hedge de ${HEDGE_STAKE:.2f}")

                        # PROTOCOLO DE STOP-LOSS ANTECIPADO: Vender cotas da posicao perdedora na CLOB
                        # Escudo Anti-Whipsaw (>= 215s) + Escudo Anti-Sweep Ziad Francis (Veto de wicks sem fechamento estrutural)
                        if elapsed >= 215:
                            sweep_check = evaluate_anti_sweep_shield(
                                symbol="BTCUSDT",
                                window_ts=window_ts,
                                elapsed=elapsed,
                                target_side=target_side,
                                strike=strike,
                                current_spot=cur_b_spot,
                                current_delta=current_delta,
                                twap_delta=current_twap_delta
                            )
                            if sweep_check["is_sweep"]:
                                if elapsed % 10 < 3:
                                    print(f"    [🛡️ ANTI-SWEEP SHIELD (ZIAD ALGO)]: Veto de Stop-Loss aos {elapsed}s! {sweep_check['reason']}")
                            else:
                                sl_data = self._execute_emergency_stop_loss(target_token, target_side, shares, window_ts)
                                if sl_data["success"]:
                                    sold_early = True
                                    has_primary = False
                                    early_sell_tx_hash = sl_data["tx_hash"]
                                    early_sell_price = sl_data["price"]
                                    early_sell_payout = sl_data["payout"]
                        else:
                            if elapsed % 10 < 4:
                                print(f"       [🛡️ Anti-Whipsaw Shield]: {elapsed}s < 215s. Repique transitório suspeito. Aguardando confirmação antes de estopar.")

                # ── ADD-ON 3: BONEREAPER LATE-WINDOW SALVAGE & DUAL ALIGNMENT GATE (255s-288s) ──
                # Se estamos na reta final (255s a 288s), com posição aberta desprotegida,
                # e o Spot cruzou o strike para o lado perdedor ou há divergência fatal Spot vs TWAP:
                if has_primary and not sold_early and not hedged and 255 <= elapsed <= 288:
                    spot_losing = (target_side == "UP" and current_delta < -3.0) or \
                                  (target_side == "DOWN" and current_delta > 3.0)
                    
                    # Checagem de divergência fatal TWAP vs Spot (Lição do Ciclo 158)
                    twap_spot_divergence = (target_side == "UP" and current_twap_delta > 0 and current_delta < -5.0) or \
                                           (target_side == "DOWN" and current_twap_delta < 0 and current_delta > 5.0)

                    if spot_losing or twap_spot_divergence:
                        ob_salvage = get_clob_orderbook(target_token)
                        bid_salvage = ob_salvage["best_bid"] if ob_salvage else 0.0
                        if bid_salvage >= STOP_LOSS_MIN_BID:
                            print(f"\n    [🚨 BONEREAPER LATE-WINDOW SALVAGE]: Reta final ({elapsed}s/300s) com Spot no lado perdedor!")
                            print(f"       Spot Delta: ${current_delta:+.2f} | TWAP Delta: ${current_twap_delta:+.2f} | Best Bid: ${bid_salvage:.2f}")
                            print(f"       Estancando perda total antes da expiração a zero...")
                            sl_data = self._execute_emergency_stop_loss(target_token, target_side, shares, window_ts)
                            if sl_data.get("success"):
                                sold_early = True
                                has_primary = False
                                early_sell_tx_hash = sl_data["tx_hash"]
                                early_sell_price = sl_data["price"]
                                early_sell_payout = sl_data["payout"]

                # --- ADD-ON 2: BTC5MScour Sweeper (Desativado em modo Sniper Purista - EV negativo) ---
                if SCOUR_ENABLED and not has_primary and not sold_early and not hedged and not scour_executed and not scour_attempted and elapsed >= 240:
                    if abs(current_delta) >= SCOUR_DELTA_THRESHOLD:
                        cand_scour_side = "UP" if current_delta > 0 else "DOWN"
                        cand_scour_token = token_up if cand_scour_side == "UP" else token_down

                        # Confirmacao de Convergencia Binance para evitar sweep em oraculo atrasado
                        b_spot = get_binance_spot()
                        b_open = self.binance_opens.get(window_ts, binance_spot)
                        b_drift = (b_spot - b_open) if (b_spot and b_open) else current_delta
                        binance_ok = (cand_scour_side == "UP" and b_drift >= 5.0) or (cand_scour_side == "DOWN" and b_drift <= -5.0)

                        # Validacao de CVD Tick Data no Sweeper: Rejeita se houver agressao institucional contraria violenta
                        cvd_net = 0.0
                        cvd_sig = "NEUTRAL"
                        cvd_src = "None"
                        if binance_ok and self.cvd_watcher:
                            cvd_sweep = self.cvd_watcher.get_window_cvd(window_seconds=elapsed)
                            cvd_net = cvd_sweep.get("net_cvd_usd", 0.0)
                            cvd_sig = cvd_sweep.get("dominant_signal", "NEUTRAL")
                            cvd_src = cvd_sweep.get("source", "WS")
                            if cand_scour_side == "UP" and cvd_net < -800_000 and cvd_sig == "DOWN":
                                if elapsed % 10 < 4:
                                    print(f"       [🛡️ FILTRO CVD SWEEPER]: Rejeitando varredura em UP! CVD fortemente vendedor (${cvd_net/1e6:+.2f}M, {cvd_src}).")
                                binance_ok = False
                            elif cand_scour_side == "DOWN" and cvd_net > 800_000 and cvd_sig == "UP":
                                if elapsed % 10 < 4:
                                    print(f"       [🛡️ FILTRO CVD SWEEPER]: Rejeitando varredura em DOWN! CVD fortemente comprador (${cvd_net/1e6:+.2f}M, {cvd_src}).")
                                binance_ok = False

                        if binance_ok:
                            cand_price = 0.0
                            ask_size = 0.0
                            ob_scour = get_clob_orderbook(cand_scour_token)
                            if ob_scour and ob_scour.get("top_ask_size", 0.0) >= 1.0:
                                cand_price = ob_scour["best_ask"]
                                ask_size = ob_scour["top_ask_size"]

                            # Faixa de Risco/Retorno Positivo ($0.50 a $0.82 -> lucro min de +$0.22/dolar)
                            if SCOUR_MIN_PRICE <= cand_price <= SCOUR_MAX_PRICE:
                                cur_bal = self.get_usdc_balance()
                                if cur_bal >= FIXED_STAKE and not self._is_past_deadline(window_ts, 290):
                                    scour_attempted = True
                                    print(f"\n    [🦅 BTC5MSCOUR SWEEPER DISPARADO!] Aos {elapsed}s: Delta Chainlink de ${current_delta:+.2f} (>= ${SCOUR_DELTA_THRESHOLD:.2f})!")
                                    print(f"       Binance Drift: ${b_drift:+.2f} | CVD Líquido: ${cvd_net/1e6:+.2f}M ({cvd_src}) | CLOB Best Ask: ${cand_price:.2f} ({ask_size:.1f} cotas)")
                                    print(f"       Varrendo com ${FIXED_STAKE:.2f} USDC em {cand_scour_side}...")
                                    order_limit_p = min(SCOUR_MAX_PRICE, round(cand_price + 0.01, 2))
                                    scour_res = self.place_live_order(cand_scour_token, "BUY", FIXED_STAKE, price=order_limit_p, max_price=SCOUR_MAX_PRICE)
                                    if scour_res.get("status") == "SUCCESS":
                                        sc_resp = scour_res.get("response", {})
                                        scour_order_id = sc_resp.get("orderID") or "EXECUTED"
                                        sc_hashes = sc_resp.get("transactionsHashes") or []
                                        scour_tx_hash = sc_hashes[0] if sc_hashes else scour_order_id
                                        scour_price = cand_price
                                        if self.execution_mode == "paper":
                                            scour_executed = True
                                            scour_side = cand_scour_side
                                            scour_token = cand_scour_token
                                            scour_shares = round(FIXED_STAKE / max(0.01, cand_price), 4)
                                            print(f"       -> [MODO PAPER] SWEEPER SIMULADO! Tx: {scour_tx_hash} | {scour_shares:.4f} cotas @ ${scour_price:.2f}")
                                        else:
                                            real_sc_tok = 0.0
                                            for _ in range(3):
                                                time.sleep(1.5)
                                                real_sc_tok = self.get_token_balance(cand_scour_token)
                                                if real_sc_tok > 0:
                                                    break
                                            if real_sc_tok > 0:
                                                scour_executed = True
                                                scour_side = cand_scour_side
                                                scour_token = cand_scour_token
                                                scour_shares = real_sc_tok
                                                print(f"       -> SWEEPER EXECUTADO! Tx: {scour_tx_hash} | {scour_shares:.4f} cotas reais @ ${scour_price:.2f}")
                                            else:
                                                print(f"       [AVISO SWEEPER] Ordem enviada mas cota nao preenchida (FAK). Sweeper desconsiderado.")
                                                scour_executed = False
                                    else:
                                        print(f"       [Falha no sweeper]: {scour_res.get('error')}")
                            elif cand_price > SCOUR_MAX_PRICE:
                                if elapsed % 10 < 4:
                                    print(f"       [🛡️ EV ASSIMÉTRICO RECUSADO]: Cotação ${cand_price:.2f} > ${SCOUR_MAX_PRICE:.2f} (Lucro de apenas +${1.0-cand_price:.2f} insuficiente para arriscar $1.00).")
                        else:
                            if elapsed % 10 < 4:
                                print(f"       [Sweeper em Espera] Binance Drift (${b_drift:+.2f}) aguardando convergência com {cand_scour_side}.")

                # Log de status
                if elapsed % 10 < 4:
                    status_desc = []
                    if sold_early:
                        status_desc.append(f"Vendido Antecipado (TP ${early_sell_payout:.2f} 💰)")
                    elif has_primary:
                        status_desc.append(f"Primário {target_side}")
                    if hedged:
                        status_desc.append(f"Hedge {hedge_side} 🛡️")
                    if scour_executed:
                        status_desc.append(f"Sweeper {scour_side} 🦅")
                    if not status_desc:
                        status_desc.append("Sem posição aberta")
                    desc_str = " | ".join(status_desc)
                    print(f"       [{elapsed}s/300s] Chainlink: ${current_chainlink:,.2f} (Delta: {current_delta:+.2f}) | {desc_str}")

            time.sleep(3.5)

        # Aguarda fechamento final e resolucao oficial
        now_after_loop = int(time.time())
        remaining = max(1, 300 - (now_after_loop - window_ts) + 4)
        print(f"\n    Aguardando fechamento da vela e liquidacao oficial ({remaining}s restantes)...")
        time.sleep(remaining)

        # 8. Apuracao do Resultado Provisorio via Oraculo / Polymarket
        # Tentativa rapida (2 retries = ~6s): se ja liquidou na Polymarket, adota imediatamente
        official_winner = get_polymarket_resolution(window_ts, max_retries=2)

        # Se ainda nao liquidou na API, usa a média TWAP acumulada da Chainlink como apuração provisória
        final_chainlink = last_candle_chainlink or get_chainlink_price() or spot_eval
        twap_tracker.add_sample(final_chainlink)
        final_delta = final_chainlink - strike
        final_twap = twap_tracker.get_current_twap()
        final_twap_delta = twap_tracker.get_twap_delta()
        chainlink_twap_winner = "UP" if final_twap_delta >= 0 else "DOWN"

        print(f"\n    [🏁 APURAÇÃO FINAL]: Spot Final: ${final_chainlink:,.2f} (Delta Spot: ${final_delta:+.2f})")
        print(f"       TWAP Final Acumulado: ${final_twap:,.2f} (Delta TWAP: ${final_twap_delta:+.2f}) -> Vencedor Oráculo TWAP: {chainlink_twap_winner}")

        if official_winner:
            winner = official_winner
            winner_source = "POLYMARKET_OFFICIAL"
        else:
            winner = chainlink_twap_winner
            winner_source = "CHAINLINK_TWAP_ORACLE (PROVISORIO)"

        # Payouts calculation
        if sold_early:
            payout_primary = early_sell_payout
        elif has_primary:
            primary_win = (target_side == winner)
            payout_primary = round(shares * 1.00, 2) if primary_win else 0.00
        else:
            payout_primary = 0.00

        hedge_win = (hedged and hedge_side == winner)
        payout_hedge = round(hedge_shares * 1.00, 2) if hedge_win else 0.00

        scour_win = (scour_executed and scour_side == winner)
        payout_scour = round(scour_shares * 1.00, 2) if scour_win else 0.00

        total_payout = round(payout_primary + payout_hedge + payout_scour, 2)
        total_stake = 0.0
        if has_primary or sold_early:
            total_stake += primary_stake
        if hedged:
            total_stake += HEDGE_STAKE
        if scour_executed:
            total_stake += FIXED_STAKE

        if total_stake == 0.0:
            print(f"    [Ciclo Concluído] Nenhuma aposta realizada nesta rodada. Aguardando próxima janela...")
            return

        cycle_pnl = round(total_payout - total_stake, 2)
        self.cycles_executed += 1
        self.session_cycles += 1
        self.total_spent += total_stake

        if sold_early and scour_executed:
            res_str = "VITORIA DUPLA (TP + SCOUR)"
        elif sold_early:
            res_str = "VITORIA (TAKE PROFIT ANTECIPADO)" if cycle_pnl >= 0 else "DEFESA (STOP LOSS ANTECIPADO)"
        elif scour_executed and not (has_primary or sold_early):
            res_str = "VITORIA (SCOUR SWEEPER)" if scour_win else "DERROTA (SCOUR SWEEPER)"
        elif hedged:
            res_str = "VITORIA (HEDGE)" if cycle_pnl >= 0 else "DEFESA (PERDA MINIMIZADA)"
        elif cycle_pnl >= 0:
            res_str = "VITORIA"
        else:
            res_str = "DERROTA"

        if cycle_pnl >= 0:
            self.wins += 1
            self.session_wins += 1
        else:
            self.losses += 1
            self.session_losses += 1

        self.cumulative_cycle_pnl = round(self.cumulative_cycle_pnl + cycle_pnl, 2)

        # Se houve payout ganho na expiração (posição segurada até o fim, não vendida antecipadamente via TP/SL),
        # as cotas vencedoras na carteira Safe aguardam resgate (redeemPositions) para se tornarem USDC colateral.
        unredeemed_this_cycle = 0.0
        if not sold_early:
            if has_primary and (target_side == winner):
                unredeemed_this_cycle += payout_primary
            if hedged and (hedge_side == winner):
                unredeemed_this_cycle += payout_hedge
            if scour_executed and (scour_side == winner):
                unredeemed_this_cycle += payout_scour
        if unredeemed_this_cycle > 0:
            self.session_pending_unredeemed = round(self.session_pending_unredeemed + unredeemed_this_cycle, 2)
            self.pending_unredeemed_payouts = round(self.pending_unredeemed_payouts + unredeemed_this_cycle, 2)
            print(f"       [RECONCILIAÇÃO ON-CHAIN]: +${unredeemed_this_cycle:.2f} em cotas vencedoras aguardando resgate/redeem para USDC.")

        # Aguarda brevemente para refletir saldo no relayer
        if total_payout > 0 and self.execution_mode != "paper":
            time.sleep(3.0)
        previous_balance = self.current_balance
        new_balance = self.get_usdc_balance()
        if new_balance < 0:
            new_balance = self.current_balance

        # Se o saldo USDC aumentou na carteira (redeem processado pelo relayer ou manual), abate dos pendentes
        usdc_gain = round(new_balance - previous_balance, 2)
        if usdc_gain > 0:
            if self.session_pending_unredeemed > 0:
                self.session_pending_unredeemed = max(0.0, round(self.session_pending_unredeemed - usdc_gain, 2))
            if self.pending_unredeemed_payouts > 0:
                self.pending_unredeemed_payouts = max(0.0, round(self.pending_unredeemed_payouts - usdc_gain, 2))

        self.current_balance = new_balance

        # Atualizacao do P&L Real da Sessao medido exclusivamente na carteira (Truth Source)
        wallet_session_delta = round(new_balance - self.session_initial_balance, 2)
        self.session_pnl = wallet_session_delta
        total_pnl_vs_deposit = round(new_balance - self.initial_deposit, 2)
        self.session_pnl_trades = round(self.session_pnl_trades + cycle_pnl, 2)

        # Verificacao de paridade contabil REAL (Trades da Sessão vs Delta Real na Carteira Safe + Cotas Pendentes da Sessão)
        if self.execution_mode != "paper":
            sol_impact = get_shared_wallet_sol_impact()
            # Desconta o impacto de operações do Desk 2 (SOL) que utilizam a mesma carteira Safe compartilhada
            btc_wallet_session_delta = round(wallet_session_delta - sol_impact, 2)
            # Saldo efetivo reconciliado da sessão: variacao de USDC na sessão atribuível ao BTC + cotas pendentes da sessão
            effective_wallet_delta = round(btc_wallet_session_delta + self.session_pending_unredeemed, 2)
            expected_balance_by_trades = round(self.session_initial_balance + self.session_pnl_trades, 2)
            parity_gap = round(self.session_pnl_trades - effective_wallet_delta, 2)
            if abs(parity_gap) > 1.50:
                print(f"\n    [⚠️ ALERTA DE PARIDADE CONTÁBIL]: Divergência de ${abs(parity_gap):.2f} detectada na sessão!")
                print(f"       Resultado Teórico dos Trades da Sessão: {self.session_pnl_trades:+.2f} USDC (Esperado: ${expected_balance_by_trades:.2f})")
                print(f"       Variação USDC Total na Carteira:        {wallet_session_delta:+.2f} USDC (Atual: ${new_balance:.2f})")
                if abs(sol_impact) > 0.001:
                    print(f"       Impacto Desks Compartilhados (SOL/BTC15M): {sol_impact:+.2f} USDC")
                print(f"       Cotas Pendentes de Resgate da Sessão:   +${self.session_pending_unredeemed:.2f} USDC")
                print(f"       Delta Efetivo Reconciliado BTC:         {effective_wallet_delta:+.2f} USDC")
                if parity_gap > 3.50:
                    print(f"       [🚨 CIRCUIT BREAKER]: Vazamento de capital não reconciliado (${parity_gap:.2f} > $3.50). Congelando novas entradas para auditoria.")
                    self.is_halted = True
                    self.halt_reason = f"Vazamento contábil de carteira (${parity_gap:.2f})"
                elif parity_gap < -3.50:
                    print(f"       [ℹ️ SUPERÁVIT DE CARTEIRA]: Carteira com superávit (+${abs(parity_gap):.2f}) decorrente de resgates ou outros desks ativos. Operação regular mantida.")

            # Travas de Drawdown Pós-Ciclo
            if new_balance < DRAWDOWN_FLOOR_USDC:
                print(f"       [🚨 CIRCUIT BREAKER]: Saldo real (${new_balance:.2f}) atingiu o piso mínimo (${DRAWDOWN_FLOOR_USDC:.2f} USDC). Encerrando operações após registro.")
                self.is_halted = True
                self.halt_reason = f"Piso absoluto de capital atingido (${new_balance:.2f} < ${DRAWDOWN_FLOOR_USDC:.2f})"
            elif btc_wallet_session_delta <= -MAX_SESSION_DRAWDOWN:
                print(f"       [🚨 CIRCUIT BREAKER]: Drawdown da sessão (${btc_wallet_session_delta:.2f}) atingiu limite máximo (-${MAX_SESSION_DRAWDOWN:.2f} USDC). Encerrando operações após registro.")
                self.is_halted = True
                self.halt_reason = f"Max session drawdown atingido (${btc_wallet_session_delta:.2f} <= -${MAX_SESSION_DRAWDOWN:.2f})"

        self.traded_windows.add(window_ts)

        self.recent_winners.append(winner)
        if len(self.recent_winners) > 10:
            self.recent_winners.pop(0)

        win_rate = round(self.wins / self.cycles_executed * 100, 1) if self.cycles_executed > 0 else 0.0

        print(f"\n    ================ APURACAO CICLO #{self.cycles_executed} ================")
        print(f"    Strike Chainlink: ${strike:,.2f} | Fechamento Chainlink: ${final_chainlink:,.2f} (Delta: {final_delta:+.2f})")
        print(f"    Vencedor Oficial: {winner} ({winner_source})")
        if sold_early:
            print(f"    💰 SirMartingale TP: Venda antecipada de {shares:.2f} cotas @ ${early_sell_price:.2f} -> Payout Travado: ${early_sell_payout:.2f}")
        elif has_primary:
            print(f"    Aposta Primária: {target_side} | Payout: ${payout_primary:.2f}")
        if hedged:
            print(f"    🛡️ Hedge Bonereaper: {hedge_side} (${HEDGE_STAKE:.2f}) | Vencedor Hedge: {'SIM' if hedge_win else 'NAO'} | Payout: ${payout_hedge:.2f}")
        if scour_executed:
            print(f"    🦅 Sweeper BTC5MScour: {scour_side} (${FIXED_STAKE:.2f} @ ${scour_price:.2f}) | Vencedor: {'SIM' if scour_win else 'NAO'} | Payout: ${payout_scour:.2f}")
        print(f"    Resultado: {res_str} | P&L Rodada: {cycle_pnl:+.2f} USDC")
        print(f"    SESSAO ATUAL: {self.session_cycles} trades | Win: {self.session_wins}V/{self.session_losses}D | P&L Sessao: {self.session_pnl:+.2f} USDC")
        print(f"    SALDO REAL EM CONTA: ${new_balance:.2f} USDC (P&L Total vs $21: {total_pnl_vs_deposit:+.2f} USDC)")
        print(f"    ============================================================")

        # 9. Salva no Diario de Bordo CSV
        chosen_side = target_side if (has_primary or sold_early) else (scour_side if scour_executed else "-")
        chosen_token = target_token if (has_primary or sold_early) else (scour_token if scour_executed else "-")
        chosen_order_id = order_id if (has_primary or sold_early) else (scour_order_id or "SCOUR")
        chosen_tx = tx_hash if (has_primary or sold_early) else scour_tx_hash
        chosen_price = estimated_price if (has_primary or sold_early) else scour_price
        chosen_shares = shares if (has_primary or sold_early) else scour_shares

        with self.journal_lock:
            with open(self.journal_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    self.cycles_executed, window_ts, round(strike, 2), round(spot_eval, 2),
                    round(delta, 2), chosen_side, chosen_token, chosen_order_id, "SUCCESS",
                    chosen_tx, round(chosen_price, 3), chosen_shares, round(final_chainlink, 2), winner, res_str,
                    total_payout, cycle_pnl, self.session_pnl, round(new_balance, 2),
                    "SIM" if hedged else "NAO", hedge_side if hedged else "-", hedge_tx_hash, hedge_shares, payout_hedge,
                    "SIM" if sold_early else "NAO", early_sell_price,
                    "SIM" if scour_executed else "NAO", scour_side if scour_executed else "-", scour_tx_hash
                ])

            # 10. Salva no JSON consolidado
            trade_entry = {
                "cycle": self.cycles_executed,
                "timestamp": datetime.now().isoformat(),
                "window_ts": window_ts,
                "time_str": time_str,
                "strike_chainlink": round(strike, 2),
                "final_spot_chainlink": round(final_chainlink, 2),
                "final_twap_chainlink": round(final_twap, 2),
                "final_twap_delta": round(final_twap_delta, 2),
                "target_side": target_side if (has_primary or sold_early) else None,
                "winner": winner,
                "winner_source": winner_source,
                "result": res_str,
                "tx_hash": chosen_tx,
                "price": round(chosen_price, 3),
                "shares": chosen_shares,
                "sold_early": sold_early,
                "early_sell_price": early_sell_price,
                "early_sell_tx_hash": early_sell_tx_hash,
                "early_sell_payout": early_sell_payout,
                "hedged": hedged,
                "hedge_side": hedge_side if hedged else None,
                "hedge_tx_hash": hedge_tx_hash if hedged else None,
                "hedge_shares": hedge_shares if hedged else 0.0,
                "hedge_payout": payout_hedge,
                "scour_executed": scour_executed,
                "scour_side": scour_side if scour_executed else None,
                "scour_tx_hash": scour_tx_hash if scour_executed else None,
                "scour_shares": scour_shares,
                "scour_payout": payout_scour,
                "total_stake": total_stake,
                "total_payout": total_payout,
                "cycle_pnl": cycle_pnl,
                "session_pnl": self.session_pnl,
                "balance": new_balance
            }

            json_data = {
                "mode": f"{self.execution_mode.upper()}_TRADING_V2_CHAINLINK_BONEREAPER_SIRMARTINGALE_SCOUR",
                "execution_mode": self.execution_mode,
                "funder": self.funder_address,
                "session_initial_balance": self.session_initial_balance,
                "cycles_executed": self.cycles_executed,
                "session_cycles": self.session_cycles,
                "session_wins": self.session_wins,
                "session_losses": self.session_losses,
                "wins": self.wins,
                "losses": self.losses,
                "win_rate": win_rate,
                "total_spent": self.total_spent,
                "session_pnl": self.session_pnl,
                "total_pnl_vs_deposit": total_pnl_vs_deposit,
                "current_balance": new_balance,
                "pending_unredeemed_payouts": self.pending_unredeemed_payouts,
                "last_updated": datetime.now().isoformat(),
                "trades": []
            }
            if os.path.exists(self.journal_json):
                try:
                    with open(self.journal_json, "r", encoding="utf-8") as f:
                        prev = json.load(f)
                        json_data["trades"] = prev.get("trades", [])
                except Exception:
                    pass
            json_data["trades"].append(trade_entry)
            _atomic_json_write(self.journal_json, json_data)

        # 11. Enfileira para Reconciliacao Assincrona oficial (2-3 min apos fechamento da vela)
        if total_stake > 0:
            reconcile_item = {
                "cycle": self.cycles_executed,
                "window_ts": window_ts,
                "tentative_winner": winner,
                "target_side": target_side if (has_primary or sold_early) else None,
                "has_primary": has_primary,
                "sold_early": sold_early,
                "early_sell_payout": early_sell_payout,
                "shares": shares,
                "hedged": hedged,
                "hedge_side": hedge_side,
                "hedge_shares": hedge_shares,
                "scour_executed": scour_executed,
                "scour_side": scour_side,
                "scour_shares": scour_shares,
                "total_stake": total_stake
            }
            self.reconciliation_queue.put(reconcile_item)

    def start_loop(self):
        """Loop continuo de negociacao real com lock de instancia e tratamento robusto"""
        print("=" * 65)
        print("[LIVE V2] POLYMARKET BTC 5M - INICIANDO ENGINE DE NEGOCIACAO")
        print(f"Modo de Execucao: {self.execution_mode.upper()}")
        print(f"Carteira Funder (Proxy): {self.funder_address}")
        print(f"Aposta Fixa: ${FIXED_STAKE:.2f} USDC | Stop Loss: ${MAX_LOSS_LIMIT:.2f} | Take Profit: ${TAKE_PROFIT_LIMIT:.2f}")
        print("=" * 65)

        lock_path = os.path.join(BASE_DIR, "live_trader.lock")
        self.lock_file = _acquire_instance_lock(lock_path)
        print(f"-> Instance Lock adquirido com sucesso: {lock_path}")

        try:
            while not self.is_halted:
                try:
                    self.run_trading_cycle()
                except KeyboardInterrupt:
                    print("\n[Robo pausado pelo usuario]")
                    break
                except Exception as e:
                    print(f"[Erro critico no ciclo]: {e}")
                    import traceback
                    traceback.print_exc()
                    time.sleep(5)
        finally:
            if self.lock_file:
                try:
                    self.lock_file.close()
                except Exception:
                    pass
                try:
                    if os.path.exists(lock_path):
                        os.remove(lock_path)
                except Exception:
                    pass
            print("-> Instance Lock liberado com sucesso.")

        if self.is_halted:
            print(f"\n[OPERACOES ENCERRADAS]: {self.halt_reason}")

if __name__ == "__main__":
    trader = LiveTrader()
    trader.start_loop()
