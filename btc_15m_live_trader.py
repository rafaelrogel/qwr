"""
Desk 3B — Polymarket BTC 15-Minute Live Trader
================================================================================
Modo: LIVE (Negociacao Real na Polygon CLOB V2 via Safe 1271)
Funder: 0xE00Bd7989108c9016cCF4479ce03BaCa09f6314c (Polygon Safe)
Mercado: btc-updown-15m-{window_ts} (Polymarket Gamma API)
Janela: 900 segundos (15 minutos)
Ponto de Entrada: 500s (55% da vela — Sweet spot JEV SystemOne)
Deadband: $25.00 minimo (3.0 bps do strike)
Stake: $1.00 USDC Fixo (Condicao estrita JEV para transicao)
Piso de Seguranca Safe: $15.00 USDC

Arquitetura de Isolamento (JEV Anti-Nonce/Anti-Collision com Desk 1):
  - Client Order Namespace: d3b_live_{action}_{timestamp}
  - Diario Exclusivo: desk3b_btc15m_live_journal.json
  - Estado Exclusivo: desk3b_btc15m_live_state.json
  - Lock File: btc_15m_live.lock
================================================================================
"""
import os
import sys

# Garante UTF-8 no Windows (sem crash de emoji)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import time
import json
import urllib.request
import traceback
import msvcrt
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from py_clob_client_v2 import (
    ClobClient,
    SignatureTypeV2,
    MarketOrderArgsV2,
    OrderArgsV2,
    OrderType,
    BalanceAllowanceParams,
    AssetType
)

from anti_sweep_shield import evaluate_anti_sweep_shield
from risk_gate import check_asia_session_drift_gate, atomic_write_json, record_desk_trade_result
from execution_math import (
    calculate_sardine_zscore,
    lookup_sardine_empirical_probability,
    check_round_number_barrier,
    detect_dow_regime_15m,
    calculate_black_scholes_digital_fv,
    safe_eval_gate
)
from variable_bench import bench
from jev_microstructure_gate import jev_gate
from binance_cvd_watcher import get_cvd_watcher

cvd_watcher = get_cvd_watcher()

def _global_exception_handler(exc_type, exc_val, exc_tb):
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desk3b_live_crash.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n[{datetime.now(timezone.utc).isoformat()}] CRASH:\n")
        traceback.print_exception(exc_type, exc_val, exc_tb, file=f)
    sys.__excepthook__(exc_type, exc_val, exc_tb)

sys.excepthook = _global_exception_handler

# ============================================================
#  CONSTANTES — CALIBRADAS PARA BTC 15M LIVE (JEV SystemOne)
# ============================================================
BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
ENV_PATH         = os.path.join(BASE_DIR, ".env")
STATE_JSON       = os.path.join(BASE_DIR, "desk3b_btc15m_live_state.json")
JOURNAL_JSON     = os.path.join(BASE_DIR, "desk3b_btc15m_live_journal.json")
LOCK_PATH        = os.path.join(BASE_DIR, "btc_15m_live.lock")

WINDOW_SIZE      = 900      # 15 minutos em segundos
ENTRY_POINT      = 500      # Entrada aos 500s (55% da vela) — Consenso JEV
TP_POINT         = 620      # Take-profit monitoramento apos 620s
CLOSE_POINT      = 870      # Encerramento forcado aos 870s se sem resolucao
FIXED_STAKE      = 1.00     # Stake fixo micro-institucional JEV ($1.00 USDC)
DRAWDOWN_FLOOR_USDC = 15.00 # Piso de seguranca compartilhado da Polygon Safe

# Filtros recalibrados para 15m (JEV: assimetria positiva estrita - Alinhado ao Desk 1)
DEADBAND_FLOOR   = 25.0     # Drift minimo em USD para entrar ($25 vs $17.52 no 5m)
DEADBAND_BPS     = 0.00030  # 3.0 bps do strike
PRIMARY_MIN_PRICE = 0.40    # Preco minimo de cota (elimina penny trap)
PRIMARY_MAX_PRICE = 0.55    # Preco maximo estrito Sniper JEV (Alinhado a Desk 1: elimina compras caras > 55¢ com risco de repique)
STOP_LOSS_MIN_BID = 0.15    # Preco minimo de bid aceitavel para Stop-Loss de emergencia
HARD_INVALIDATION_DELTA_USD = 25.0  # Invalidação dura JEV: se reversão > $25, anula Anti-Sweep e liquida imediatamente
SPREAD_MAX       = 0.05     # Spread maximo toleravel no CLOB (5¢)
BINANCE_DRIFT_UP  = -8.0   # Drift Binance minimo para UP
BINANCE_DRIFT_DOWN = 8.0   # Drift Binance maximo para DOWN

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

def _acquire_instance_lock(lock_file_path: str):
    try:
        f = open(lock_file_path, "w")
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        return f
    except (IOError, OSError):
        print(f"[BLOQUEIO] Ja existe uma instancia do Desk 3B LIVE em execucao ({lock_file_path}). Abortando.")
        sys.exit(0)

# ============================================================
#  CLIENTE POLYMARKET CLOB V2 (Safe 1271)
# ============================================================
class PolymarketLiveClob:
    def __init__(self):
        self.cfg = load_env_config()
        self.private_key = self.cfg.get("POLYGON_PRIVATE_KEY", "").strip()
        if self.private_key.startswith("0x"):
            self.private_key = self.private_key[2:]
        self.funder_address = self.cfg.get("POLY_FUNDER_ADDRESS", "").strip()
        self.signer_address = self.cfg.get("POLY_SIGNER_ADDRESS", "").strip()
        self.client: Optional[ClobClient] = None
        self._init_clob()

    def _init_clob(self):
        if not self.private_key or not self.funder_address:
            print("[ERRO FATAL] Credenciais Polygon Safe nao encontradas no .env!")
            sys.exit(1)
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
            print(f"   -> [CLOB V2 CONECTADO]: Safe 1271 Funder {self.funder_address} autenticado com sucesso!")
        except Exception as e:
            print(f"[ERRO ao conectar ClobClient]: {e}")
            self.client = None

    def get_usdc_balance(self) -> float:
        if not self.client:
            return 0.0
        try:
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            info = self.client.get_balance_allowance(params)
            raw_bal = float(info.get("balance", 0.0))
            return round(raw_bal / 1e6, 4)
        except Exception as e:
            print(f"   [Aviso Saldo USDC]: {e}")
            return 0.0

    def get_token_balance(self, token_id: str) -> float:
        if not self.client or not token_id:
            return 0.0
        try:
            params = BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
            info = self.client.get_balance_allowance(params)
            raw_bal = float(info.get("balance", 0.0))
            return round(raw_bal / 1e6, 4)
        except Exception:
            return 0.0

    def place_market_order(self, token_id: str, side: str, amount: float, price: float) -> dict:
        if not self.client:
            return {"status": "ERROR", "error": "ClobClient desconectado"}
        try:
            market_args = MarketOrderArgsV2(
                token_id=token_id,
                amount=amount,
                side=side,
                price=price,
                order_type=OrderType.FAK
            )
            signed = self.client.create_market_order(market_args)
            resp = self.client.post_order(signed, order_type=OrderType.FAK)
            return {"status": "SUCCESS", "response": resp}
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

    def place_post_only_order(self, token_id: str, side: str, price: float, size: float) -> dict:
        if not self.client:
            return {"status": "ERROR", "error": "ClobClient desconectado"}
        try:
            order_args = OrderArgsV2(
                token_id=token_id,
                price=price,
                size=size,
                side=side
            )
            signed = self.client.create_order(order_args)
            resp = self.client.post_order(signed, order_type=OrderType.GTC, post_only=True)
            return {"status": "SUCCESS", "response": resp}
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}

# ============================================================
#  FUNCOES DE MERCADO E FEEDS
# ============================================================
def get_binance_spot() -> Optional[float]:
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
            req = urllib.request.Request(rpc, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=2.5) as r:
                res = json.loads(r.read().decode("utf-8"))
                if "result" in res and res["result"] and len(res["result"]) >= 130:
                    ans_hex = res["result"][66:130]
                    price = int(ans_hex, 16) / 1e8
                    if price > 10000:
                        return round(price, 2)
        except Exception:
            continue
    return None

def get_candle_open_15m(window_ts: int) -> Optional[float]:
    url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=3"
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

def get_polymarket_15m_market(window_ts: int) -> Optional[Dict[str, Any]]:
    slug = f"btc-updown-15m-{window_ts}"
    url = f"https://gamma-api.polymarket.com/events?slug={slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PolymarketSettler/2.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
            if isinstance(data, list) and len(data) > 0:
                markets = data[0].get("markets", [])
                if markets:
                    return markets[0]
            elif isinstance(data, dict):
                markets = data.get("markets", [])
                if markets:
                    return markets[0]
    except Exception:
        pass

    url_search = "https://gamma-api.polymarket.com/markets?limit=30&active=true&closed=false"
    try:
        req = urllib.request.Request(url_search, headers={"User-Agent": "PolymarketSettler/2.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            mkts = json.loads(r.read().decode())
            for m in mkts:
                q = m.get("question", "")
                if "Bitcoin Up or Down" in q and ("15 min" in q or "15m" in q or "15-Minute" in q):
                    ed = m.get("endDate") or m.get("end_date_iso")
                    if ed:
                        return m
    except Exception:
        pass
    return None

def get_clob_orderbook_15m(token_id: str) -> Optional[Dict[str, Any]]:
    """Consulta order book L2 do token (read-only — sem autenticacao)"""
    url = f"https://clob.polymarket.com/book?token_id={token_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Desk3BLiveBot/1.0"})
        with urllib.request.urlopen(req, timeout=3.5) as r:
            book = json.loads(r.read().decode())
            bids = [(float(b["price"]), float(b["size"])) for b in book.get("bids", [])
                    if "price" in b and "size" in b and float(b["size"]) >= 1.0]
            asks = [(float(a["price"]), float(a["size"])) for a in book.get("asks", [])
                    if "price" in a and "size" in a and float(a["size"]) >= 1.0]
            if not bids or not asks:
                return None
            best_bid = max(bids, key=lambda x: x[0])[0]
            best_ask = min(asks, key=lambda x: x[0])[0]
            top_bid_sz = max(bids, key=lambda x: x[0])[1]
            top_ask_sz = min(asks, key=lambda x: x[0])[1]
            spread = best_ask - best_bid
            microprice = (best_bid * top_ask_sz + best_ask * top_bid_sz) / (top_bid_sz + top_ask_sz) \
                if (top_bid_sz + top_ask_sz) > 0 else (best_bid + best_ask) / 2.0
            
            # Métricas de Order Flow Imbalance (OFI L2)
            sum_bids = sum(b[1] for b in sorted(bids, key=lambda x: -x[0])[:5])
            sum_asks = sum(a[1] for a in sorted(asks, key=lambda x: x[0])[:5])
            top_imbalance = (top_bid_sz - top_ask_sz) / (top_bid_sz + top_ask_sz) if (top_bid_sz + top_ask_sz) > 0 else 0.0
            depth_imbalance = (sum_bids - sum_asks) / (sum_bids + sum_asks) if (sum_bids + sum_asks) > 0 else 0.0

            return {
                "best_bid": round(best_bid, 4),
                "best_ask": round(best_ask, 4),
                "spread": round(spread, 4),
                "microprice": round(microprice, 4),
                "bid_vol": round(top_bid_sz, 2),
                "ask_vol": round(top_ask_sz, 2),
                "sum_bids": round(sum_bids, 2),
                "sum_asks": round(sum_asks, 2),
                "top_imbalance": round(top_imbalance, 3),
                "depth_imbalance": round(depth_imbalance, 3),
            }
    except Exception:
        pass
    return None

def get_polymarket_15m_resolution(window_ts: int, max_retries: int = 36) -> Optional[str]:
    slug = f"btc-updown-15m-{window_ts}"
    url = f"https://gamma-api.polymarket.com/events?slug={slug}"
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PolymarketSettler/2.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())
                if isinstance(data, list) and len(data) > 0:
                    markets = data[0].get("markets", [])
                    if markets:
                        mkt = markets[0]
                        outcome_prices = json.loads(mkt.get("outcomePrices", "[]")) if isinstance(mkt.get("outcomePrices"), str) else mkt.get("outcomePrices", [])
                        if outcome_prices:
                            p_up = float(outcome_prices[0]) if len(outcome_prices) > 0 else 0.0
                            p_down = float(outcome_prices[1]) if len(outcome_prices) > 1 else 0.0
                            if p_up >= 0.98:
                                return "UP"
                            elif p_down >= 0.98:
                                return "DOWN"
                        if mkt.get("closed"):
                            prices = json.loads(mkt.get("outcomePrices", "[]"))
                            if prices and float(prices[0]) > 0.5:
                                return "UP"
                            elif prices and float(prices[1]) > 0.5:
                                return "DOWN"
        except Exception:
            pass
        time.sleep(5)
    return None

# ============================================================
#  JOURNAL E ESTADO LIVE
# ============================================================
def load_journal() -> Dict:
    if os.path.exists(JOURNAL_JSON):
        try:
            with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "mode": "LIVE",
        "funder": "0xE00Bd7989108c9016cCF4479ce03BaCa09f6314c",
        "current_balance": 25.89,
        "initial_balance": 25.89,
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "total_pnl": 0.0,
        "trades": []
    }

def save_journal(journal: Dict):
    atomic_write_json(JOURNAL_JSON, journal)

def save_state(state: Dict):
    atomic_write_json(STATE_JSON, state)

# ============================================================
#  CICLO PRINCIPAL LIVE
# ============================================================
def run_cycle(clob: PolymarketLiveClob, journal: Dict) -> Dict:
    now = time.time()
    window_ts = (int(now) // WINDOW_SIZE) * WINDOW_SIZE
    elapsed = now - window_ts
    seconds_left = WINDOW_SIZE - elapsed

    live_balance = clob.get_usdc_balance()
    if live_balance > 0:
        journal["current_balance"] = live_balance

    state = {
        "window_ts": window_ts,
        "seconds_elapsed": int(elapsed),
        "seconds_left": int(seconds_left),
        "progress_pct": round(elapsed / WINDOW_SIZE * 100, 1),
        "mode": "LIVE",
        "balance": live_balance,
        "stake": FIXED_STAKE,
        "status_signal": "Aguardando ponto de entrada",
        "last_update": datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S UTC")
    }

    # Piso de protecao de margem compartilhado Safe
    if live_balance < DRAWDOWN_FLOOR_USDC:
        print(f"\n   [🚨 PISO DE SEGURANCA SAFE]: Saldo Safe (${live_balance:.2f}) < Piso (${DRAWDOWN_FLOOR_USDC:.2f}). Abortando ciclo.")
        state["status_signal"] = f"Piso de Seguranca Atingido (${live_balance:.2f} < ${DRAWDOWN_FLOOR_USDC:.2f})"
        save_state(state)
        time.sleep(30)
        return journal

    # Se ja operou esta janela no diario LIVE, nao reentra
    existing_windows = set(t.get("window_ts") for t in journal.get("trades", []))
    if window_ts in existing_windows:
        state["status_signal"] = f"Janela {window_ts} ja operada nesta sessao"
        save_state(state)
        time.sleep(min(30, max(1, int(seconds_left) + 2)))
        return journal

    # Checagem do Variable Bench e Disjuntores (Universal 2-Loss + Coin-Flip - JEV AI)
    is_benched, bench_reason, bench_rem = bench.check_consecutive_losses_breaker("desk3b", journal.get("trades", []), max_consecutive_losses=2, cooldown_seconds=1800)
    if not is_benched:
        is_benched, bench_reason, bench_rem = bench.check_coin_flip_breaker("desk3b", journal.get("trades", []))
    if not is_benched:
        is_benched, bench_reason, bench_rem = bench.is_benched("desk3b")
    if is_benched:
        print(f"   [🛑 VARIABLE BENCH]: Desk 3B em cooldown ({bench_reason}) — restam {bench_rem:.1f}s. Aguardando...")
        state["status_signal"] = f"Bench Cooldown ({bench_reason}: {bench_rem:.0f}s)"
        save_state(state)
        time.sleep(min(15, max(2, int(bench_rem))))
        return journal

    # Aguarda ponto quantitativo aos 500s (55% da vela)
    if elapsed < ENTRY_POINT:
        wait_s = ENTRY_POINT - elapsed
        if int(elapsed) % 20 == 0:
            print(f"   [AGUARDANDO ENTRADA LIVE]: {int(elapsed)}s elapsed. Entrada aos {ENTRY_POINT}s. Aguardando {int(wait_s)}s... (Saldo: ${live_balance:.2f} USDC)")
        state["status_signal"] = f"Aguardando Ponto {ENTRY_POINT}s ({int(elapsed)}s/{ENTRY_POINT}s)"
        save_state(state)
        time.sleep(min(10, max(1, int(wait_s))))
        return journal

    # Ponto de decisao aos 500s
    print("\n" + "="*80)
    print(f"   [PONTO DE DECISAO LIVE {ENTRY_POINT}s]: Avaliando entrada BTC 15m Polymarket...")
    print(f"   Saldo Real Safe: ${live_balance:.2f} USDC | Stake Fixo: ${FIXED_STAKE:.2f} USDC")
    print("="*80)

    # 1. Mercado Gamma API
    market = get_polymarket_15m_market(window_ts)
    if not market:
        print("   [SEM MERCADO]: Mercado de 15m nao encontrado na Gamma API. Pulando.")
        state["status_signal"] = "Mercado nao encontrado"
        save_state(state)
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    tokens = json.loads(market.get("clobTokenIds", "[]")) if isinstance(market.get("clobTokenIds"), str) else market.get("clobTokenIds", [])
    outcome_prices = json.loads(market.get("outcomePrices", "[]")) if isinstance(market.get("outcomePrices"), str) else market.get("outcomePrices", [])
    question = market.get("question", "")
    active = market.get("active", False)

    print(f"   Mercado: {question}")
    p_up_disp = float(outcome_prices[0]) if len(outcome_prices) > 0 else 0.5
    p_down_disp = float(outcome_prices[1]) if len(outcome_prices) > 1 else 0.5
    print(f"   Active: {active} | UP: ${p_up_disp:.3f} | DOWN: ${p_down_disp:.3f}")

    if not active:
        print("   [MERCADO INATIVO]: Pulando janela.")
        state["status_signal"] = "Mercado inativo"
        save_state(state)
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    # 2. Strike da janela
    strike = get_candle_open_15m(window_ts) or get_chainlink_price() or get_binance_spot()
    if not strike:
        print("   [SEM STRIKE]: Impossivel obter preco de referencia. Pulando.")
        state["status_signal"] = "Sem preco de referencia"
        save_state(state)
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    state["strike"] = round(strike, 2)

    # 3. Spot atual (Chainlink)
    spot = get_chainlink_price() or get_binance_spot()
    if not spot:
        print("   [SEM SPOT]: Impossivel obter spot actual. Pulando.")
        state["status_signal"] = "Sem spot actual"
        save_state(state)
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    state["spot"] = round(spot, 2)
    delta = spot - strike
    state["delta"] = round(delta, 2)

    # 3.1 Escudo de Discrepância Lead-Lag de Oráculo (Portado do Desk 1 / Consenso JEV 100%)
    binance_spot = get_binance_spot()
    binance_drift = (binance_spot - strike) if binance_spot else 0.0
    if binance_spot:
        oracle_discrepancy = abs(binance_spot - spot)
        max_discrepancy = max(MAX_ORACLE_STRIKE_DISCREPANCY_FLOOR_USD, round(strike * MAX_ORACLE_STRIKE_DISCREPANCY_BPS, 2))
        if oracle_discrepancy > max_discrepancy:
            print(f"   [🛡️ VETO DISCREPÂNCIA LEAD-LAG]: Spread Binance (${binance_spot:,.2f}) vs Chainlink (${spot:,.2f}) = ${oracle_discrepancy:.2f} > Máx ${max_discrepancy:.2f}!")
            print(f"      Oráculo Chainlink defasado em relação ao mercado à vista. Abortando para evitar convergência tóxica.")
            state["status_signal"] = f"Veto Oráculo Lead-Lag (${oracle_discrepancy:.1f})"
            save_state(state)
            bench.sit("desk3b", "oracle_lead_lag_discrepancy", custom_seconds=max(30, int(seconds_left) + 2))
            time.sleep(max(1, int(seconds_left) + 5))
            return journal

    # 4. Detecção de Regime Charles Dow & Deadband dinâmico (Raghee Horner / JEV)
    dow_info = detect_dow_regime_15m(symbol="BTCUSDT")
    dow_mult = dow_info.get("deadband_multiplier", 1.0)
    dow_rec_shares = dow_info.get("recommended_contracts", 2)
    print(f"   [🏛️ DOW REGIME DETECTOR]: {dow_info.get('description')}")

    deadband_dyn = max(DEADBAND_FLOOR, strike * DEADBAND_BPS * dow_mult)
    state["deadband"] = round(deadband_dyn, 2)
    print(f"   Strike: ${strike:,.2f} | Spot: ${spot:,.2f} | Delta: ${delta:+.2f} | Deadband: ${deadband_dyn:.2f} ({DEADBAND_BPS*10000*dow_mult:.1f} bps)")

    if abs(delta) < deadband_dyn:
        print(f"   [FILTRO DEADBAND]: |Delta| ${abs(delta):.2f} < Deadband ${deadband_dyn:.2f}. Sem sinal claro.")
        state["status_signal"] = f"Deadband — Delta ${delta:+.2f} / Piso ${deadband_dyn:.2f}"
        save_state(state)
        bench.sit("desk3b", "deadband_noise", custom_seconds=max(30, int(seconds_left) + 2))
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    # 5. Direcao
    target_side = "UP" if delta > 0 else "DOWN"
    print(f"   Direcao: {target_side} (Delta ${delta:+.2f})")

    # 5.0 Veto de Contratendência no Dow Regime (Consenso JEV / Raghee Horner)
    dow_regime = dow_info.get("regime", "")
    dow_slope = dow_info.get("slope_bps", 0.0)
    reversal_mult = 2.5
    strong_reversal_threshold = round(deadband_dyn * reversal_mult, 2)

    if dow_regime == "DOWNTREND" and target_side == "UP":
        if delta < strong_reversal_threshold:
            print(f"   [🛡️ VETO DOW REGIME - JEV]: Tentativa de comprar UP contra Tendência de Baixa ativa (Slope: {dow_slope:+.1f} bps).")
            print(f"      Delta de +${delta:.2f} é repique fraco (< ${strong_reversal_threshold:.2f} exigidos para contratendência). Abortando para preservar capital.")
            state["status_signal"] = f"Veto Dow Regime (Downtrend slope {dow_slope:.1f} bps)"
            save_state(state)
            bench.sit("desk3b", "dow_countertrend_veto", custom_seconds=max(30, int(seconds_left) + 2))
            time.sleep(max(1, int(seconds_left) + 5))
            return journal
        else:
            print(f"   [🔥 OVERRIDE DOW REVERSAL]: Delta massivo de +${delta:.2f} superou {reversal_mult}x deadband (${strong_reversal_threshold:.2f}). Reversão validada.")

    elif dow_regime == "UPTREND" and target_side == "DOWN":
        if abs(delta) < strong_reversal_threshold:
            print(f"   [🛡️ VETO DOW REGIME - JEV]: Tentativa de comprar DOWN contra Tendência de Alta ativa (Slope: {dow_slope:+.1f} bps).")
            print(f"      Delta de -${abs(delta):.2f} é correção fraca (< ${strong_reversal_threshold:.2f} exigidos para contratendência). Abortando para preservar capital.")
            state["status_signal"] = f"Veto Dow Regime (Uptrend slope {dow_slope:.1f} bps)"
            save_state(state)
            bench.sit("desk3b", "dow_countertrend_veto", custom_seconds=max(30, int(seconds_left) + 2))
            time.sleep(max(1, int(seconds_left) + 5))
            return journal
        else:
            print(f"   [🔥 OVERRIDE DOW REVERSAL]: Delta massivo de -${abs(delta):.2f} superou {reversal_mult}x deadband (${strong_reversal_threshold:.2f}). Reversão validada.")

    # 5.1 Round Number Barrier Shield (.00 Double Zero - Raghee Horner / JEV)
    is_barrier, barrier_reason = check_round_number_barrier(spot=spot, target_side=target_side, interval=500.0, buffer_usd=20.0)
    if is_barrier:
        print(f"   [🛡️ ROUND NUMBER SHIELD]: {barrier_reason}. Abortando entrada para evitar ricochete.")
        state["status_signal"] = f"Veto Round Barrier ({barrier_reason[:30]}...)"
        save_state(state)
        bench.sit("desk3b", "round_number_barrier", custom_seconds=max(30, int(seconds_left) + 2))
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    # 6. Confirmacao Binance
    binance_spot = get_binance_spot()
    if binance_spot:
        binance_drift = binance_spot - strike
        print(f"   Binance drift: ${binance_drift:+.2f}")
        if target_side == "UP" and binance_drift < BINANCE_DRIFT_UP:
            print(f"   [FILTRO BINANCE]: Drift Binance ${binance_drift:+.2f} < ${BINANCE_DRIFT_UP:.1f} para UP. Abortando.")
            state["status_signal"] = f"Veto Binance Drift ({binance_drift:+.1f})"
            save_state(state)
            bench.sit("desk3b", "binance_drift_counter", custom_seconds=max(30, int(seconds_left) + 2))
            time.sleep(max(1, int(seconds_left) + 5))
            return journal
        elif target_side == "DOWN" and binance_drift > BINANCE_DRIFT_DOWN:
            print(f"   [FILTRO BINANCE]: Drift Binance ${binance_drift:+.2f} > ${BINANCE_DRIFT_DOWN:.1f} para DOWN. Abortando.")
            state["status_signal"] = f"Veto Binance Drift ({binance_drift:+.1f})"
            save_state(state)
            bench.sit("desk3b", "binance_drift_counter", custom_seconds=max(30, int(seconds_left) + 2))
            time.sleep(max(1, int(seconds_left) + 5))
            return journal

    # 6.1 Gate de Sessao Asiatica
    try:
        asia_ok, asia_reason, asia_info = check_asia_session_drift_gate(target_side=target_side)
        if not asia_ok:
            print(f"   [🛡️ ASIA DRIFT GATE]: Trade {target_side} bloqueado: {asia_reason}!")
            state["status_signal"] = f"Veto Asia Drift Gate ({asia_info.get('asia_drift_bps', 0.0):+.1f} bps)"
            save_state(state)
            time.sleep(max(1, int(seconds_left) + 5))
            return journal
    except Exception:
        pass

    # 6.2 Validacao Empirica Sardine Base-Rate (10k janelas)
    try:
        z_score = calculate_sardine_zscore(spot=spot, strike=strike, realized_vol_60m=0.55, seconds_remaining=seconds_left)
        p_sardine, n_sardine, _ = lookup_sardine_empirical_probability(z_score=z_score, seconds_remaining=seconds_left)
        if p_sardine is not None:
            empirical_favors = (target_side == "UP" and p_sardine >= 0.52) or (target_side == "DOWN" and p_sardine <= 0.48)
            print(f"   [📊 SARDINE BASE-RATE]: Z={z_score:+.2f} | P(UP)={p_sardine:.1%} (n={n_sardine}) | Favorece {target_side}: {empirical_favors}")
            if (target_side == "UP" and p_sardine < 0.45) or (target_side == "DOWN" and p_sardine > 0.55):
                print(f"   [🛡️ VETO SARDINE BASE-RATE]: Historico de 10k janelas desfavorece {target_side} (P={p_sardine:.1%}). Abortando trade armadilha.")
                state["status_signal"] = f"Veto Sardine Base-Rate ({p_sardine:.1%})"
                save_state(state)
                time.sleep(max(1, int(seconds_left) + 5))
                return journal
    except Exception as e:
        print(f"   [Sardine Base-Rate Info]: {e}")

    # 7. Order Book L2
    token_idx = 0 if target_side == "UP" else 1
    target_token = tokens[token_idx] if len(tokens) > token_idx else None
    entry_price = None

    if target_token:
        ob = get_clob_orderbook_15m(target_token)
        if ob:
            entry_price = ob["best_ask"]
            spread = ob["spread"]
            microprice = ob["microprice"]
            print(f"   CLOB L2: Best Ask=${entry_price:.3f} | Spread=${spread:.3f} | Microprice=${microprice:.4f}")
            if spread > SPREAD_MAX:
                print(f"   [FILTRO SPREAD]: Spread ${spread:.3f} > max ${SPREAD_MAX:.3f}. Abortando.")
                state["status_signal"] = f"Veto Spread CLOB (${spread:.3f})"
                save_state(state)
                bench.sit("desk3b", "clob_spread_wide", custom_seconds=max(30, int(seconds_left) + 2))
                time.sleep(max(1, int(seconds_left) + 5))
                return journal

            # 7.1 OFI L2 IMBALANCE GATE (PolyResearch / JEV AI anti-false-breakout)
            top_imb = ob.get("top_imbalance", 0.0)
            depth_imb = ob.get("depth_imbalance", 0.0)
            print(f"   [📊 OFI L2 ORDER BOOK]: Imbalance L1={top_imb:+.2f} | Depth L5={depth_imb:+.2f} (Bids: {ob.get('sum_bids', 0.0):.0f} vs Asks: {ob.get('sum_asks', 0.0):.0f})")

            # Muralha tóxica contrária: se o token possui muralha massiva de venda (Ask Wall)
            # desbalanceamento fortemente negativo (top < -0.30 e depth < -0.25):
            if top_imb < -0.30 and depth_imb < -0.25:
                # Salvaguarda Anti-Starvation: Override APENAS se Delta E Drift Binance confirmarem forte impulso direcional
                binance_confirms = (binance_drift is not None) and (
                    (target_side == "UP" and binance_drift >= (1.75 * DEADBAND_FLOOR)) or
                    (target_side == "DOWN" and binance_drift <= -(1.75 * DEADBAND_FLOOR))
                )
                if abs(delta) >= (1.75 * DEADBAND_FLOOR) and binance_confirms:
                    print(f"   [🔥 OVERRIDE OFI IMBALANCE]: Muralha detectada, mas Delta (+${abs(delta):.2f}) E Binance drift (${binance_drift:+.2f}) confirmaram absorção institucional.")
                else:
                    print(f"   [🛡️ VETO OFI L2 IMBALANCE]: Muralha de venda institucional (Ask Wall) detectada no token {target_side} (L1: {top_imb:+.2f}, L5: {depth_imb:+.2f}).")
                    print(f"      Alto risco de falso rompimento/rejeição no final da vela de 15m. Abortando entrada para preservar capital.")
                    state["status_signal"] = f"Veto OFI Imbalance ({top_imb:+.2f})"
                    save_state(state)
                    bench.sit("desk3b", "clob_liquidity_thin", custom_seconds=max(30, int(seconds_left) + 2))
                    time.sleep(max(1, int(seconds_left) + 5))
                    return journal
            else:
                print(f"   [✅ OFI L2 IMBALANCE APROVADO]: Fluxo de ordens equilibrado ou favorável para {target_side}.")

            # 7.2 DETECTOR DE VELOCIDADE LEAD-LAG (Polymarket 2025 Bot Model)
            velo_data = cvd_watcher.get_velocity_lead_lag(window_seconds=3.0, min_velocity_threshold=12.0)
            v_usd_s = velo_data.get("velocity_usd_sec", 0.0)
            v_disp = velo_data.get("price_displacement", 0.0)
            v_dir = velo_data.get("direction", "NEUTRAL")

            if velo_data.get("is_high_velocity", False):
                if (target_side == "UP" and v_dir == "DOWN") or (target_side == "DOWN" and v_dir == "UP"):
                    print(f"   [🛡️ VETO VELOCIDADE ADVERSA (SPEED GAP LEAD-LAG)]: Binance acelerando contra {target_side} ({v_usd_s:+.1f} $/s, deslocamento: ${v_disp:+.1f})!")
                    print(f"      Alto risco de ser atropelado pela Binance no fechamento da janela de 2.7s. Abortando entrada.")
                    state["status_signal"] = f"Veto Velocidade Adversa ({v_usd_s:+.1f} $/s)"
                    save_state(state)
                    bench.sit("desk3b", "binance_velocity_counter", custom_seconds=max(30, int(seconds_left) + 2))
                    time.sleep(max(1, int(seconds_left) + 5))
                    return journal
                elif (target_side == "UP" and v_dir == "UP") or (target_side == "DOWN" and v_dir == "DOWN"):
                    print(f"   [⚡ ALTA CONVICÇÃO LEAD-LAG]: Binance acelerando forte a favor de {target_side} ({v_usd_s:+.1f} $/s, deslocamento: ${v_disp:+.1f})!")

    if not entry_price:
        entry_price = float(outcome_prices[token_idx])

    # ── HYBRID BLACK-SCHOLES FAIR VALUE GATE (100% VALIDADO JEV AI — BACKTEST 9 ANOS) ──
    bs_prob_up = calculate_black_scholes_digital_fv(
        spot=spot,
        strike=strike,
        elapsed_sec=int(WINDOW_SIZE - seconds_left),
        total_sec=WINDOW_SIZE,
        sigma=0.0030
    )
    target_fv = bs_prob_up if target_side == "UP" else round(1.0 - bs_prob_up, 4)
    # Teto Hibrido: menor valor entre o teto estatico de 0.55 e o Valor Justo mais tolerancia de spread de 2c (+0.02)
    hybrid_max_price = min(PRIMARY_MAX_PRICE, max(PRIMARY_MIN_PRICE, round(target_fv + 0.02, 3)))

    if entry_price > hybrid_max_price:
        print(f"   [🛡️ GATE HIBRIDO BLACK-SCHOLES]: Preco ${entry_price:.3f} excede Teto Hibrido de ${hybrid_max_price:.3f} (Valor Justo BS: ${target_fv:.3f} + 0.02 spread | Cap Estatico: ${PRIMARY_MAX_PRICE:.2f}). Abortando com Negative EV.")
        state["status_signal"] = f"Veto BS Hibrido (${entry_price:.3f} > ${hybrid_max_price:.3f})"
        save_state(state)
        bench.sit("desk3b", "bs_negative_ev", custom_seconds=max(30, int(seconds_left) + 2))
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    if entry_price < PRIMARY_MIN_PRICE:
        print(f"   [FILTRO PRECO PISO JEV]: Preco ${entry_price:.3f} < ${PRIMARY_MIN_PRICE:.2f}. Abortando.")
        state["status_signal"] = f"Veto Preco Piso (${entry_price:.3f})"
        save_state(state)
        bench.sit("desk3b", "price_out_of_bounds", custom_seconds=max(30, int(seconds_left) + 2))
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    # Estrategia Maker Touch Quoting vs Taker
    is_maker = False
    touch_price = entry_price
    if target_token and ob:
        best_bid = ob.get("best_bid", 0.0)
        best_ask = ob.get("best_ask", 0.0)
        if spread >= 0.02 and best_bid > 0 and (best_bid + 0.01) <= hybrid_max_price:
            touch_price = round(best_bid + 0.01, 3)
            is_maker = True

    # ── JEV MICROSTRUCTURE GATE (MODO LIVE CALIBRADO) ──────────────────────────
    oracle_disc = abs((binance_spot or spot) - spot) if binance_spot else 0.0
    clob_spread_val = spread if (target_token and ob) else 0.03
    obi_val = ob.get("top_imbalance", 0.0) if ob else 0.0
    jev_eval = jev_gate.evaluate_entry(
        desk_id="desk3b",
        delta_usd=delta,
        binance_drift=binance_drift if binance_spot else 0.0,
        clob_spread=clob_spread_val,
        contract_price=touch_price,
        oracle_discrepancy=oracle_disc,
        seconds_left=int(seconds_left),
        obi=obi_val,
        cvd=0.0,
        deadband_threshold=deadband_dyn,
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
        print(f"\n   [🧠 JEV ADVISORY - VETO OBSERVADO]: {jev_eval.get('veto_reason')}")
        print(f"      -> Regime: {jev_regime} | Score: {jev_score} | {jev_ms}ms | (MODO ADVISORY: trade continua)")
        state["status_signal"] = f"JEV Advisory VETO observado ({jev_regime})"
    else:
        print(f"   [🧠 JEV ADVISORY]: Regime: {jev_regime} | Score: {jev_score} | Veredito: {jev_verdict} ({jev_ms}ms)")

    # Arquitetura Raghee Horner / JEV: 2.0 cotas em tendência (Scale-Out: 50% TP1 @ 86c + Runner Breakeven)
    # Calibração Dinâmica JEV: Em regime de distribuição/choppy (dow_rec_shares == 1), escala para lote mínimo do CLOB V2 ($1.05 USDC)!
    target_shares = float(dow_rec_shares)
    raw_stake = round(target_shares * touch_price, 2)
    # Polymarket CLOB V2 exige piso mínimo de $1.00 USDC por ordem marketable
    stake_usd = max(1.05, raw_stake)
    shares = round(stake_usd / touch_price, 4)
    now_utc_str = datetime.fromtimestamp(time.time(), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S UTC")

    # Margem de slippage de ate 1.5c para evitar rejeicao FAK por flutuacao de milissegundos
    buy_limit_price = min(hybrid_max_price, round(touch_price + 0.015, 3))
    print(f"\n   ⚡ [BOLETAGEM REAL POLYMARKET CLOB V2 (2-STAGE SCALE)]: Enviando {target_side} @ ${touch_price:.3f} (Limite FAK: ${buy_limit_price:.3f}) | {shares:.1f} cotas | Stake: ${stake_usd:.2f} USDC...")
    
    order_res = clob.place_market_order(
        token_id=target_token,
        side="BUY",
        amount=stake_usd,
        price=buy_limit_price
    )

    if order_res.get("status") != "SUCCESS":
        print(f"   [❌ FALHA NA EXECUCAO CLOB]: {order_res.get('error')}. Abortando.")
        state["status_signal"] = f"Falha na Execucao CLOB: {order_res.get('error')}"
        save_state(state)
        time.sleep(max(1, int(seconds_left) + 5))
        return journal

    resp_data = order_res.get("response", {})
    order_id = resp_data.get("orderID") or resp_data.get("order_id", "LIVE_EXEC")
    print(f"   -> [ORDEM EXECUTADA COM SUCESSO]: ID: {order_id} | Shares: {shares:.4f}")

    # Atualiza saldo real apos compra
    time.sleep(2)
    post_buy_bal = clob.get_usdc_balance()
    if post_buy_bal > 0:
        journal["current_balance"] = post_buy_bal

    state["status_signal"] = f"LIVE {target_side} @ ${touch_price:.3f} (ID: {order_id[:10]}...) — Monitorando 2 Cotas..."
    state["entry_side"] = target_side
    state["entry_price"] = touch_price
    state["entry_time"] = now_utc_str
    state["tp1_executed"] = False
    save_state(state)

    # ── MONITORAMENTO POS-ENTRADA COM DEFESA ATIVA (BONEREAPER & SIRMARTINGALE) ──
    cur_time = time.time()
    cur_elapsed = cur_time - window_ts

    while cur_elapsed < WINDOW_SIZE + 30:
        cur_elapsed = time.time() - window_ts
        remaining = WINDOW_SIZE - cur_elapsed

        if target_token:
            ob_now = get_clob_orderbook_15m(target_token)
            if ob_now:
                cur_price = ob_now.get("best_bid", touch_price)
                cur_pnl = (cur_price - touch_price) * shares
                state["current_price"] = cur_price
                state["unrealized_pnl"] = round(cur_pnl, 4)

                # 1. BONEREAPER STOP-LOSS (Defesa Antecipada contra Reversao de Delta)
                cur_spot = get_chainlink_price() or get_binance_spot()
                if cur_spot:
                    live_delta = cur_spot - strike
                    reversed_delta = (target_side == "UP" and live_delta < -DEADBAND_FLOOR) or \
                                     (target_side == "DOWN" and live_delta > DEADBAND_FLOOR)
                else:
                    live_delta = delta
                    reversed_delta = False

                sl_threshold = max(STOP_LOSS_MIN_BID, round(touch_price * 0.60, 3))

                # 1.0 CÃO DE GUARDA SENTINELA JEV (Saída Antecipada contra Reversão em Andamento)
                if cur_elapsed >= ENTRY_POINT + 30 and not state.get("tp1_executed", False) and cur_price >= STOP_LOSS_MIN_BID:
                    watchdog_eval = jev_gate.evaluate_in_trade_watchdog(
                        desk_id="desk3b",
                        symbol="BTC",
                        side=target_side,
                        entry_price=touch_price,
                        current_price=cur_price,
                        current_delta=live_delta,
                        delta_at_entry=delta,
                        seconds_left=int(remaining),
                        clob_bid=cur_price
                    )
                    if watchdog_eval.get("action") == "EMERGENCY_EXIT":
                        print(f"\n   🚨 [CÃO DE GUARDA JEV LIVE]: {watchdog_eval.get('reason')}. Executando saída de emergência @ ${cur_price:.3f}...")
                        real_shares = clob.get_token_balance(target_token) or shares
                        sl_limit = max(STOP_LOSS_MIN_BID, round(cur_price - 0.02, 3))
                        sell_res = clob.place_market_order(token_id=target_token, side="SELL", amount=real_shares, price=sl_limit)
                        if sell_res.get("status") == "SUCCESS":
                            final_price = cur_price
                            final_pnl = round((final_price - touch_price) * shares, 4)
                            bench.sit("desk3b", "jev_watchdog_exit")
                            journal = _register_trade(journal, window_ts, target_side, touch_price, final_price, target_shares, final_pnl, "DEFESA_JEV_WATCHDOG", live_delta, clob)
                            save_state({**state, "status_signal": f"LIVE SAÍDA JEV @ ${final_price:.3f} | PnL ${final_pnl:+.4f}"})
                            time.sleep(max(1, int(remaining) + 10))
                            return journal

                if reversed_delta and cur_price <= sl_threshold and cur_elapsed >= ENTRY_POINT + 45 and not state.get("tp1_executed", False):
                    # Invalidação Dura JEV: Se a reversão exceder $35 USD além do strike, é reversão confirmada (bypassa Anti-Sweep)
                    reversal_mag = abs(live_delta)
                    is_hard_invalidation = (reversal_mag >= HARD_INVALIDATION_DELTA_USD)

                    if not is_hard_invalidation:
                        sweep_check = evaluate_anti_sweep_shield(
                            symbol="BTCUSDT",
                            window_ts=window_ts,
                            elapsed=cur_elapsed,
                            target_side=target_side,
                            strike=strike,
                            current_spot=cur_spot or spot,
                            current_delta=live_delta,
                            twap_delta=None
                        )
                        if sweep_check.get("is_sweep") and cur_elapsed < 800:
                            time.sleep(5)
                            continue
                    else:
                        print(f"\n   ⚡ [HARD INVALIDATION JEV]: Reversão adversa de ${reversal_mag:.2f} >= ${HARD_INVALIDATION_DELTA_USD:.2f}! Ignorando Anti-Sweep Shield para liquidação imediata.")

                    if cur_price >= STOP_LOSS_MIN_BID:
                        print(f"\n   🚨 [DEFESA BONEREAPER STOP-LOSS REAL]: Reversao detectada ({live_delta:+.2f}). Vendendo antecipado @ ${cur_price:.3f}...")
                        real_shares = clob.get_token_balance(target_token) or shares
                        sl_limit_price = max(STOP_LOSS_MIN_BID, round(cur_price - 0.02, 3))
                        sell_res = clob.place_market_order(token_id=target_token, side="SELL", amount=real_shares, price=sl_limit_price)
                        print(f"      -> Venda Stop-Loss status: {sell_res.get('status')}")
                        if sell_res.get("status") == "SUCCESS":
                            final_price = cur_price
                            final_pnl = round((final_price - touch_price) * shares, 4)
                            outcome_label = "DEFESA_SL"
                            bench.sit("desk3b", "post_stop_loss_15m")
                            journal = _register_trade(journal, window_ts, target_side, touch_price, final_price, target_shares, final_pnl, outcome_label, live_delta, clob)
                            save_state({**state, "status_signal": f"LIVE DEFESA SL @ ${final_price:.3f} | PnL ${final_pnl:+.4f}"})
                            time.sleep(max(1, int(remaining) + 10))
                            return journal
                        else:
                            print(f"      -> [AVISO STOP-LOSS]: Venda na CLOB falhou ({sell_res.get('error')}). Mantendo posicao...")

                # 2. SIRMARTINGALE TAKE-PROFIT COM ESCALA EM 2 ETAPAS (RAGHEE HORNER / JEV)
                if cur_price >= 0.86 and cur_elapsed >= TP_POINT and not state.get("tp1_executed", False):
                    print(f"\n   💰 [TAKE-PROFIT ETAPA 1 (50%)]: Bid bateu ${cur_price:.3f} >= $0.86 aos {int(cur_elapsed)}s. Realizando 1.0 cota na CLOB!")
                    tp_limit_price = max(0.84, round(cur_price - 0.015, 3))
                    sell_res = clob.place_market_order(token_id=target_token, side="SELL", amount=1.0, price=tp_limit_price)
                    print(f"      -> Venda TP1 status: {sell_res.get('status')}")
                    if sell_res.get("status") == "SUCCESS":
                        pnl_tp1 = round((cur_price - touch_price) * 1.0, 4)
                        state["tp1_executed"] = True
                        state["tp1_price"] = cur_price
                        state["tp1_pnl"] = pnl_tp1
                        shares = 1.0
                        save_state({**state, "status_signal": f"LIVE TP1 EXECUTADO @ ${cur_price:.3f} (+${pnl_tp1:.2f}) | Runner em Breakeven"})
                        print(f"      -> TP1 Concluído! Lucro Parcial: +${pnl_tp1:.4f} USDC | Stop da cota restante movido para Breakeven (${touch_price:.3f})!")
                    else:
                        print(f"      -> [AVISO TP1]: Venda parcial na CLOB falhou ({sell_res.get('error')}).")

                # 3. BREAKEVEN STOP-LOSS DO RUNNER (APÓS TP1)
                if state.get("tp1_executed", False):
                    if cur_price <= touch_price and cur_price >= STOP_LOSS_MIN_BID:
                        print(f"\n   🛡️ [BREAKEVEN STOP-LOSS RUNNER]: Cota restante tocou Breakeven (${cur_price:.3f} <= ${touch_price:.3f}). Liquidando a zero risco...")
                        be_limit = max(STOP_LOSS_MIN_BID, round(cur_price - 0.02, 3))
                        sell_res = clob.place_market_order(token_id=target_token, side="SELL", amount=1.0, price=be_limit)
                        if sell_res.get("status") == "SUCCESS":
                            pnl_be = round((cur_price - touch_price) * 1.0, 4)
                            total_pnl = round(state.get("tp1_pnl", 0.0) + pnl_be, 4)
                            outcome_label = "WIN_BE"
                            journal = _register_trade(journal, window_ts, target_side, touch_price, cur_price, target_shares, total_pnl, outcome_label, live_delta if cur_spot else delta, clob)
                            save_state({**state, "status_signal": f"LIVE WIN BREAKEVEN @ ${cur_price:.3f} | Total PnL ${total_pnl:+.4f}"})
                            time.sleep(max(1, int(remaining) + 10))
                            return journal

                # 4. LATE-CANDLE DELTA DECAY DEFENSE (CONSENSO JEV SYSTEMONE)
                # Protege contra repiques violentos no minuto final (750s a 860s) antes da virada da vela
                if cur_elapsed >= 750 and cur_elapsed <= 860 and not state.get("tp1_executed", False):
                    initial_delta_mag = abs(delta)
                    # Verifica se o delta inverteu de sinal:
                    delta_flipped = (target_side == "DOWN" and live_delta > 0) or (target_side == "UP" and live_delta < 0)

                    # Se não inverteu de sinal, verifica se a magnitude decaiu drasticamente:
                    if not delta_flipped:
                        favorable_delta = (-live_delta if target_side == "DOWN" else live_delta)
                        delta_decayed = (favorable_delta < (initial_delta_mag * 0.35))
                    else:
                        delta_decayed = True

                    # Se a reversão foi confirmada E ainda há liquidez/bid razoável no livro (>= $0.20):
                    if delta_decayed and cur_price >= 0.20:
                        print(f"\n   ⚠️ [LATE-CANDLE DELTA DECAY DEFENSE]: Reversão aos {int(cur_elapsed)}s detectada!")
                        print(f"      Delta inicial: {delta:+.2f} | Delta atual: {live_delta:+.2f} | Bid na CLOB: ${cur_price:.3f}")
                        print(f"      Liquidando posição antecipadamente para salvar capital residual...")
                        real_shares = clob.get_token_balance(target_token) or shares
                        decay_sl_limit = max(0.18, round(cur_price - 0.02, 3))
                        sell_res = clob.place_market_order(token_id=target_token, side="SELL", amount=real_shares, price=decay_sl_limit)
                        print(f"      -> Venda Delta Decay status: {sell_res.get('status')}")
                        if sell_res.get("status") == "SUCCESS":
                            final_price = cur_price
                            final_pnl = round((final_price - touch_price) * shares, 4)
                            outcome_label = "DEFESA_DELTA_DECAY"
                            bench.sit("desk3b", "post_delta_decay_defense_15m")
                            journal = _register_trade(journal, window_ts, target_side, touch_price, final_price, target_shares, final_pnl, outcome_label, live_delta, clob)
                            save_state({**state, "status_signal": f"LIVE DEFESA DELTA DECAY @ ${final_price:.3f} | PnL ${final_pnl:+.4f}"})
                            time.sleep(max(1, int(remaining) + 10))
                            return journal

        # Fechamento normal da janela (aguarda resolucao)
        if cur_elapsed >= WINDOW_SIZE:
            print(f"\n   [FIM DA JANELA]: Buscando resolucao oficial Polymarket...")
            resolution = get_polymarket_15m_resolution(window_ts, max_retries=36)
            if not resolution:
                # Fallback: se Gamma API demorar > 180s, verifica se o spot final Chainlink/Binance liquidou acima ou abaixo do strike
                final_spot = get_chainlink_price() or get_binance_spot()
                if final_spot and strike:
                    resolution = "UP" if final_spot >= strike else "DOWN"
                    print(f"   [RESOLUCAO FALLBACK ORACULO]: Gamma API pendente. Inferido por spot (${final_spot:,.2f} vs strike ${strike:,.2f}) -> {resolution}")
            if resolution:
                won = (resolution == target_side)
                if state.get("tp1_executed", False):
                    # Já realizou TP1 em 1 cota. A 2ª cota expira agora:
                    pnl_runner = round(1.0 - touch_price, 4) if won else -touch_price
                    total_pnl = round(state.get("tp1_pnl", 0.0) + pnl_runner, 4)
                    outcome_label = "WIN_SCALE" if won else "DEFESA_TP1"
                    exit_p = 1.0 if won else 0.0
                    pnl = total_pnl
                else:
                    pnl = round((shares * 1.0) - stake_usd, 4) if won else -stake_usd
                    outcome_label = "WIN" if won else "LOSS"
                    exit_p = 1.0 if won else 0.0
                print(f"   [RESOLUCAO LIVE]: {resolution} | Apostou: {target_side} | {'GANHOU' if won else 'PERDEU'} | PnL: ${pnl:+.4f}")
                journal = _register_trade(journal, window_ts, target_side, touch_price, exit_p, target_shares, pnl, outcome_label, delta, clob)
                save_state({**state, "status_signal": f"{'WIN' if won else 'LOSS'} @ {resolution} | PnL ${pnl:+.4f}"})
            else:
                journal = _register_trade(journal, window_ts, target_side, touch_price, touch_price, target_shares, 0.0, "VOID", delta, clob)
                save_state({**state, "status_signal": "VOID — resolucao nao obtida"})
            return journal

        save_state(state)
        time.sleep(15)
        cur_elapsed = time.time() - window_ts

    return journal

def _register_trade(journal: Dict, window_ts: int, side: str, entry: float,
                    exit_price: float, shares: float, pnl: float,
                    outcome: str, delta: float, clob: PolymarketLiveClob) -> Dict:
    journal["total_trades"] = journal.get("total_trades", 0) + 1
    if outcome in ("WIN", "WIN_TP"):
        journal["wins"] = journal.get("wins", 0) + 1
    elif outcome == "LOSS":
        journal["losses"] = journal.get("losses", 0) + 1

    total = journal["total_trades"]
    wins = journal.get("wins", 0)
    journal["win_rate"] = round(wins / total * 100, 1) if total > 0 else 0.0
    journal["total_pnl"] = round(journal.get("total_pnl", 0.0) + pnl, 4)

    # Atualiza saldo real da Safe
    time.sleep(2)
    bal_real = clob.get_usdc_balance()
    if bal_real > 0:
        journal["current_balance"] = bal_real

    trade_record = {
        "timestamp": datetime.fromtimestamp(time.time(), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S UTC"),
        "window_ts": window_ts,
        "side": side,
        "entry_price": round(entry, 4),
        "exit_price": round(exit_price, 4),
        "shares": round(shares, 4),
        "stake": FIXED_STAKE,
        "pnl": round(pnl, 4),
        "outcome": outcome,
        "delta_at_entry": round(delta, 2),
        "live_balance": journal.get("current_balance")
    }
    journal.setdefault("trades", []).append(trade_record)
    save_journal(journal)
    try:
        is_win = (outcome == "WIN") or (pnl >= 0)
        record_desk_trade_result("desk3b", is_win=is_win, pnl=pnl)
    except Exception:
        pass
    return journal

# ============================================================
#  ENTRYPOINT
# ============================================================
def main():
    lock_file = _acquire_instance_lock(LOCK_PATH)
    print("="*80)
    print("  🔥 INICIANDO DESK 3B — POLYMARKET BTC 15M LIVE ALGO TRADER")
    print("  Modo: LIVE (Dinheiro Real Polygon Safe)")
    print(f"  Funder Safe: 0xE00Bd7989108c9016cCF4479ce03BaCa09f6314c")
    print(f"  Entrada: {ENTRY_POINT}s (55% da vela) | Deadband: ${DEADBAND_FLOOR:.0f} | Stake Fixo: ${FIXED_STAKE:.2f} USDC")
    print(f"  Piso de Protecao de Margem: ${DRAWDOWN_FLOOR_USDC:.2f} USDC")
    print("="*80)

    clob = PolymarketLiveClob()
    bal = clob.get_usdc_balance()
    print(f"  -> Saldo Real em Carteira Safe: ${bal:.2f} USDC")

    journal = load_journal()
    print(f"  -> Diario LIVE Carregado: {journal['total_trades']} trades | WR: {journal['win_rate']:.1f}%")

    try:
        while True:
            try:
                journal = run_cycle(clob, journal)
                time.sleep(2)
            except KeyboardInterrupt:
                print("\n\n   [DESK 3B LIVE] Encerrado pelo utilizador.")
                break
            except Exception as e:
                print(f"\n   [ERRO CICLO DESK 3B LIVE]: {e}")
                time.sleep(10)
    finally:
        if lock_file:
            try:
                lock_file.close()
            except Exception:
                pass
            try:
                if os.path.exists(LOCK_PATH):
                    os.remove(LOCK_PATH)
            except Exception:
                pass
        print("-> Lock do Desk 3B LIVE liberado.")

if __name__ == "__main__":
    main()
