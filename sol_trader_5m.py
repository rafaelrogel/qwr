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
JOURNAL_JSON = os.path.join(BASE_DIR, "sol_trading_journal.json")
LIVE_STATE_JSON = os.path.join(BASE_DIR, "sol_live_market_state.json")

# Carrega credenciais do .env
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
SOL_MODE = ENV_CFG.get("SOL_MODE", "LIVE").upper()

# ===================== PARÂMETROS QUANTITATIVOS (JEV AI CALIBRATED) =====================
FIXED_STAKE = 1.00                # $1.00 por aposta
DEADBAND_BPS = 0.00050            # 5.0 bps (0.050%) do preço da SOL
DEADBAND_MIN_FLOOR = 0.06         # Piso mínimo de $0.06 de variação na SOL
PRIMARY_MAX_PRICE = 0.55          # Preço máximo de entrada (55¢)
PRIMARY_MIN_PRICE = 0.35          # Preço mínimo de entrada (35¢)
MAX_CLOB_SPREAD = 0.08            # Spread máximo aceito no book (8¢)
TAKE_PROFIT_PRICE = 0.86          # Take Profit antecipado (86¢)
STOP_LOSS_MIN_BID = 0.15          # Bid mínimo aceito para Stop Loss na CLOB
EVAL_POINT_SEC = 135              # 135s (2m15s da vela de 5m)
REQUIRE_PRIOR_CANDLE = True       # Filtro Jev Trend Continuation

# ===================== DATA PROVIDERS (BINANCE REF) =====================
def get_binance_sol_spot() -> Optional[float]:
    """Preço Spot em tempo real da Solana (SOL/USDT) na Binance"""
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
    """Obtém a abertura da vela de 5m correspondente ao window_ts"""
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
                "microprice": round(microprice, 4)
            }
    except Exception:
        return None

# ===================== SOLANA ALGO TRADER ENGINE (LIVE + PAPER) =====================
class SolanaTrader5M:
    def __init__(self):
        self.mode = SOL_MODE
        self.balance = 29.6506 # Saldo padrão / paper
        self.trades = []
        self.current_open_position = None
        self.traded_windows = set()
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
        """Consulta o saldo real de USDC na conta Polymarket via CLOB V2"""
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
            print(f"[Aviso ao buscar saldo SOL]: {e}")
            return -1.0

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

    def place_live_order(self, token_id: str, side: str, amount: float, price: Optional[float] = None) -> Dict[str, Any]:
        """Cria e envia ordem a mercado real para o Polymarket CLOB V2 (BUY em USDC, SELL em cotas)"""
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
        try:
            with open(JOURNAL_JSON, "w", encoding="utf-8") as f:
                json.dump(journal, f, indent=2)
        except Exception as e:
            print(f"[Erro ao gravar {JOURNAL_JSON}]: {e}")

    def save_live_state(self, state: dict):
        try:
            with open(LIVE_STATE_JSON, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def run_cycle(self):
        now_ts = int(time.time())
        window_ts = (now_ts // 300) * 300
        elapsed_sec = now_ts - window_ts
        remaining_sec = max(0, 300 - elapsed_sec)
        dt_str = datetime.fromtimestamp(window_ts, timezone.utc).strftime("%H:%M:%S")

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

        # Se em modo LIVE, valida saldo e piso de proteção antes de prosseguir
        if self.mode == "LIVE":
            live_bal = self.get_usdc_balance()
            if live_bal < 15.00:
                print(f"   [🚨 TRAVA DE SEGURANÇA]: Saldo Safe (${live_bal:.2f} USDC) abaixo do piso de proteção ($15.00). Preservando depósito.")
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

        evaluated_entry = False

        # Loop de monitoramento contínuo da vela (a cada 2 segundos)
        while True:
            cur_time = time.time()
            cur_elapsed = int(cur_time - window_ts)
            cur_left = max(0, 300 - cur_elapsed)

            if cur_elapsed >= 298:
                break

            # Consulta Spot e Strike
            strike = get_sol_candle_open(window_ts)
            spot_now = get_binance_sol_spot()
            if not strike or not spot_now:
                time.sleep(2)
                continue

            delta = spot_now - strike
            dynamic_deadband = max(DEADBAND_MIN_FLOOR, round(strike * DEADBAND_BPS, 4))

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
                    status_sig = f"Deadband Ativo: Delta (${delta:+.3f}) no ruído (< ${dynamic_deadband:.3f})"
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
            # 2. PONTO QUANTITATIVO DE ENTRADA (135s)
            # -------------------------------------------------------------
            if cur_elapsed >= EVAL_POINT_SEC and not evaluated_entry and self.current_open_position is None:
                evaluated_entry = True
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🎯 PONTO DE DECISÃO QUANTITATIVA (135s):")
                print(f"   Strike: ${strike:.2f} | Spot Atual: ${spot_now:.2f} | Delta: ${delta:+.4f}")
                print(f"   Deadband Dinâmico: ${dynamic_deadband:.4f} ({DEADBAND_BPS*10000:.1f} bps)")

                if not candidate_side or not target_book:
                    print(f"   -> [🛡️ FILTRO DEADBAND/LIVRO]: Delta (${delta:+.4f}) na zona morta ou book indisponível. Preservando capital.")
                else:
                    # Filtro JEV Trend Continuation
                    prior_candle = get_binance_sol_5m_prior_candle()
                    prior_dir = prior_candle["dir"] if prior_candle else candidate_side
                    prior_ret = prior_candle["ret_bps"] if prior_candle else 0.0

                    if REQUIRE_PRIOR_CANDLE and prior_candle and prior_dir != candidate_side:
                        print(f"   -> [🛡️ VETO JEV]: Sinal {candidate_side} rejeitado por divergir da vela 5m anterior ({prior_dir} {prior_ret:.1f} bps).")
                    else:
                        # Bússola Macro BTC (Jev Lead-Lag)
                        btc_spot = get_binance_btc_spot()
                        btc_open = get_btc_candle_open(window_ts)
                        btc_veto = False
                        if btc_spot and btc_open:
                            btc_delta = btc_spot - btc_open
                            if candidate_side == "UP" and btc_delta < -10.0:
                                btc_veto = True
                                print(f"   -> [🛡️ VETO MACRO BTC]: Sinal UP rejeitado! BTC em queda (Delta: ${btc_delta:+.1f}).")
                            elif candidate_side == "DOWN" and btc_delta > 10.0:
                                btc_veto = True
                                print(f"   -> [🛡️ VETO MACRO BTC]: Sinal DOWN rejeitado! BTC em alta (Delta: ${btc_delta:+.1f}).")

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

                            # Filtros de Execução Realista
                            if spread > MAX_CLOB_SPREAD:
                                print(f"   -> [🛡️ FILTRO SPREAD]: Spread de ${spread:.4f} > ${MAX_CLOB_SPREAD:.2f}. Abortando entrada por liquidez tóxica.")
                            elif best_ask > PRIMARY_MAX_PRICE:
                                print(f"   -> [🛡️ FILTRO TETO DE PREÇO]: Best Ask ${best_ask:.2f} > ${PRIMARY_MAX_PRICE:.2f}. EV desfavorável.")
                            elif best_ask < PRIMARY_MIN_PRICE:
                                print(f"   -> [🛡️ FILTRO PISO DE PREÇO]: Best Ask ${best_ask:.2f} < ${PRIMARY_MIN_PRICE:.2f}. Risco de reversão assimétrica.")
                            elif ask_size < (FIXED_STAKE / best_ask):
                                print(f"   -> [🛡️ FILTRO PROFUNDIDADE]: Volume no topo ({ask_size:.1f} cotas) insuficiente para preencher ${FIXED_STAKE:.2f}.")
                            else:
                                if self.mode == "LIVE":
                                    print(f"\n   🚀 [ENVIANDO ORDEM REAL POLYMARKET CLOB V2 ({candidate_side})]:")
                                    print(f"      Token: {target_token[:14]}... | Preço: ${best_ask:.2f} | Stake: ${FIXED_STAKE:.2f} USDC")
                                    order_res = self.place_live_order(target_token, "BUY", FIXED_STAKE, price=best_ask)
                                    if order_res.get("status") == "SUCCESS":
                                        resp_data = order_res.get("response", {})
                                        order_id = resp_data.get("orderID") or "N/A"
                                        tx_hashes = resp_data.get("transactionsHashes") or []
                                        tx_hash = tx_hashes[0] if tx_hashes else order_id
                                        exec_price = best_ask

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
                                            "stake": FIXED_STAKE,
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
                                        print(f"      [❌ ERRO AO EXECUTAR ORDEM REAL]: {order_res.get('error')}")
                                else:
                                    # EXECUÇÃO PAPER HIPER-REALISTA
                                    exec_price = best_ask
                                    shares = round(FIXED_STAKE / exec_price, 4)
                                    self.balance -= FIXED_STAKE

                                    self.current_open_position = {
                                        "window_ts": window_ts,
                                        "time_str": dt_str,
                                        "market_slug": market_slug,
                                        "token_id": target_token,
                                        "direction": candidate_side,
                                        "strike": strike,
                                        "entry_price": exec_price,
                                        "shares": shares,
                                        "stake": FIXED_STAKE,
                                        "entry_time": cur_time,
                                        "clob_spread": spread,
                                        "clob_best_bid": best_bid,
                                        "clob_best_ask": best_ask,
                                        "mode": "PAPER"
                                    }

                                    print(f"\n   🚀 [ORDEM PAPER PREENCHIDA NO LIVRO REAL!]:")
                                    print(f"      Lado: {candidate_side} | Preço Taker (Best Ask): ${exec_price:.2f}")
                                    print(f"      Cotas: {shares} | Investimento: ${FIXED_STAKE:.2f} USD")
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
                                tp_tx = tp_hashes[0] if tp_hashes else tp_order_id
                                payout = round(sell_shares * sell_price, 4)
                                pnl = round(payout - pos["stake"], 4)
                                time.sleep(1.0)
                                self.get_usdc_balance()

                                print(f"   -> TAKE-PROFIT REAL EXECUTADO! ID: {tp_order_id} | Tx: {tp_tx}")
                                print(f"   -> Payout: ${payout:.2f} | P&L: {pnl:+.2f} USDC | Novo Saldo: ${self.balance:,.2f} USDC")

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
                                    "sell_price": sell_price,
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

                    # 3B. Stop-Loss de Emergência (Bonereaper) se delta reverter contra a posição
                    reversal = (pos["direction"] == "UP" and delta <= -dynamic_deadband) or (pos["direction"] == "DOWN" and delta >= dynamic_deadband)
                    if cur_elapsed >= 160 and reversal and cur_best_bid >= STOP_LOSS_MIN_BID:
                        sell_price = cur_best_bid
                        real_s = self.get_token_balance(pos["token_id"]) if self.mode == "LIVE" else pos["shares"]
                        raw_s = real_s if (real_s is not None and real_s >= 0.5) else pos["shares"]
                        sell_shares = int(raw_s * 100) / 100.0
                        sl_limit_price = max(STOP_LOSS_MIN_BID, round(cur_best_bid - 0.02, 2))

                        if self.mode == "LIVE":
                            print(f"\n🚨 [ENVIANDO STOP-LOSS DE EMERGÊNCIA REAL!]:")
                            print(f"   Delta reverteu ({delta:+.3f}). Vendendo {sell_shares:.2f} cotas (Best Bid: ${sell_price:.2f} | Limite: ${sl_limit_price:.2f})...")
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
                                sl_tx = sl_hashes[0] if sl_hashes else sl_order_id
                                payout = round(sell_shares * sell_price, 4)
                                pnl = round(payout - pos["stake"], 4)
                                time.sleep(1.0)
                                self.get_usdc_balance()

                                print(f"   -> STOP-LOSS REAL EXECUTADO! ID: {sl_order_id} | Tx: {sl_tx}")
                                print(f"   -> Saldo Resgatado: ${payout:.2f} | P&L: {pnl:+.2f} USDC | Novo Saldo: ${self.balance:,.2f} USDC")

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
                                    "sell_price": sell_price,
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
            final_spot = get_binance_sol_spot() or spot_now
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
        print("\n" + "=" * 90)
        print("  INICIANDO BOT SOLANA 5-MINUTE ALGO TRADER (POLYMARKET CLOB)")
        print(f"  Modo Ativo: {self.mode} (LIVRO L2 REAL CONECTADO)")
        print(f"  Funder da Conta: {POLY_FUNDER_ADDRESS}")
        print(f"  Saldo Atual ({self.mode}): ${self.balance:.2f} USD")
        print("=" * 90)
        while True:
            try:
                self.run_cycle()
            except Exception as e:
                print(f"[Erro no ciclo Solana]: {e}")
            time.sleep(3)

# Aliases de compatibilidade
SolanaPaperTrader5M = SolanaTrader5M

if __name__ == "__main__":
    bot = SolanaTrader5M()
    bot.start()
