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
  * Drift Intra-Vela (|Delta| >= $15) e Reversao Markoviana (DDD -> UP)
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
from datetime import datetime
from typing import Optional, Dict, Any

from py_clob_client_v2 import (
    ClobClient,
    SignatureTypeV2,
    MarketOrderArgsV2,
    OrderType,
    BalanceAllowanceParams,
    AssetType
)
from binance_liquidation_watcher import get_liquidation_watcher
from binance_cvd_watcher import get_cvd_watcher
from py_clob_client_v2.order_builder.builder import ROUNDING_CONFIG

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
PRIMARY_MIN_PRICE = 0.35  # Preco minimo de cota primaria (evita penny traps)
PRIMARY_MAX_PRICE = 0.62  # Preco maximo de cota primaria (Audit PIT: fill <= 0.62 garante breakeven < 60%)
HEDGE_STAKE = 1.00        # $1.00 USDC para hedge dinamico estilo Bonereaper (min size Polymarket CLOB)
HEDGE_DELTA_THRESHOLD = 8.0  # Reversao de $8 no Chainlink aciona protecao antecipada de hedge
HEDGE_MAX_PRICE = 0.45     # Preco maximo permitido para hedge (<= $0.45 garante retorno positivo se hedged)
STOP_LOSS_MIN_BID = 0.15   # Preco minimo de bid para liquidar posicao perdedora antecipadamente (Stop-Loss)
TAKE_PROFIT_PRICE_THRESHOLD = 0.86 # Add-on 1 (SirMartingale): Venda antecipada se cotacao bater $0.86+ (lucro ~80%)
SCOUR_ENABLED = False     # Sweeper desativado (Audit Backtest provou EV negativo de -1.8c/$)
SCOUR_DELTA_THRESHOLD = 25.0 # Delta minimo para Sweeper (se habilitado)
SCOUR_MIN_PRICE = 0.50       # Preco minimo de cota para o Sweeper
SCOUR_MAX_PRICE = 0.75       # Preco maximo de cota para o Sweeper
MAX_LOSS_LIMIT = -5.00    # Stop loss diario (-$5.00 USDC)
TAKE_PROFIT_LIMIT = 50.00 # Take profit aumentado para +$50.00 USDC

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

def _atomic_json_write(path: str, data: dict):
    """Grava JSON de forma atomica usando arquivo temporario para evitar corrupcao em caso de queda"""
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception as e:
        print(f"[Erro na gravacao atomica do JSON {path}]: {e}")

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
        "https://polygon.drpc.org",
        "https://gateway.tenderly.co/public/polygon",
        "https://polygon.publicnode.com",
        "https://polygon-bor.publicnode.com"
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
                "microprice": round(microprice, 4)
            }
    except Exception as e:
        print(f"    [Erro ao consultar Order Book CLOB]: {e}")
        return None

def get_streak_snapper_signal(min_atr_mult: float = 3.0) -> Optional[Dict[str, Any]]:
    """
    Estratégia Streak Snapper (Moon Dev):
    Analisa se as últimas 4 velas completas de 5m foram na mesma direção (ex: 4x UP ou 4x DOWN)
    e se o esticamento acumulado ultrapassou 3x o ATR horário.
    Retorna o lado de reversão ('UP' ou 'DOWN') com os dados do sinal, ou None.
    """
    url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=17"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PolymarketStreakBot/2.0"})
        with urllib.request.urlopen(req, timeout=3.5) as r:
            klines = json.loads(r.read().decode())
            if not klines or len(klines) < 16:
                return None

            completed = klines[:-1] # exclui a vela em andamento
            last_12 = completed[-12:]
            trs = [max(float(k[2]) - float(k[3]), abs(float(k[2]) - float(k[1])), abs(float(k[3]) - float(k[1]))) for k in last_12]
            hourly_atr = sum(trs) / len(trs) if trs else 1.0

            last_4 = completed[-4:]
            directions = ["UP" if float(k[4]) >= float(k[1]) else "DOWN" for k in last_4]

            all_up = all(d == "UP" for d in directions)
            all_down = all(d == "DOWN" for d in directions)

            if all_up or all_down:
                streak_dir = "UP" if all_up else "DOWN"
                reversal_side = "DOWN" if all_up else "UP"
                cum_move = abs(float(last_4[-1][4]) - float(last_4[0][1]))
                atr_ratio = cum_move / hourly_atr if hourly_atr > 0 else 0.0

                if atr_ratio >= min_atr_mult:
                    return {
                        "reversal_side": reversal_side,
                        "streak_dir": streak_dir,
                        "cum_move": round(cum_move, 2),
                        "hourly_atr": round(hourly_atr, 2),
                        "atr_ratio": round(atr_ratio, 2)
                    }
    except Exception:
        pass
    return None

def check_ddd_completed_candles() -> bool:
    """
    Verifica se as ultimas 3 velas completas de 5m fecharam em queda (DOWN, DOWN, DOWN)
    a partir de klines reais da Binance (Audit 2.6).
    Evita depender de snapshots locais provisorios em memoria.
    """
    url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=5"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PolymarketBot/2.0"})
        with urllib.request.urlopen(req, timeout=3.5) as r:
            klines = json.loads(r.read().decode())
            if not klines or len(klines) < 4:
                return False
            completed = klines[:-1]  # exclui a vela em andamento
            last_3 = completed[-3:]
            return all(float(k[4]) < float(k[1]) for k in last_3)
    except Exception:
        return False

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
        self.session_cycles = 0
        self.session_wins = 0
        self.session_losses = 0

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

        self.execution_mode = self.cfg.get("EXECUTION_MODE", "live").lower()
        self.lock_file = None
        self.journal_lock = threading.Lock()
        self.traded_windows = self._load_traded_windows()
        self._init_journal()
        self._init_clob()
        self._start_async_reconciler()

    def _load_traded_windows(self) -> set:
        """Carrega todas as janelas (window_ts) ja negociadas para evitar duplicacoes no restart"""
        traded = set()
        if os.path.exists(JOURNAL_JSON):
            try:
                with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
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
        if not os.path.exists(JOURNAL_CSV):
            with open(JOURNAL_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "cycle_num", "window_ts", "strike_K", "entry_spot",
                    "delta_entry", "decision", "token_id", "order_id", "status",
                    "tx_hash", "entry_price", "shares", "final_spot", "winner", "result",
                    "payout", "cycle_pnl", "total_pnl", "balance",
                    "hedged", "hedge_decision", "hedge_tx_hash", "hedge_shares", "hedge_payout",
                    "early_sold", "early_sell_price", "scour_executed", "scour_side", "scour_tx_hash"
                ])

        if os.path.exists(JOURNAL_JSON):
            try:
                with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.total_spent = data.get("total_spent", 0.0)
                    self.wins = data.get("wins", 0)
                    self.losses = data.get("losses", 0)
                    self.cycles_executed = data.get("cycles_executed", 0)
                    self.recent_winners = [r["winner"] for r in data.get("trades", [])[-5:] if r.get("winner")]
            except Exception as ej:
                print(f"[ALERTA CRÍTICO] Falha ao ler {JOURNAL_JSON}: {ej}. Criando backup de seguranca.")
                try:
                    os.replace(JOURNAL_JSON, f"{JOURNAL_JSON}.corrupt-{int(time.time())}")
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
            self.session_initial_balance = bal
            self.current_balance = bal
            print(f"   -> Saldo Real em Carteira: ${bal:.2f} USDC (Base de Risco da Sessao Chainlink)")
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
                        if os.path.exists(JOURNAL_JSON):
                            try:
                                with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
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

                                _atomic_json_write(JOURNAL_JSON, jdata)

                                self.wins = total_w
                                self.losses = total_l
                                self.current_balance = real_bal
                                self.session_pnl = jdata["session_pnl"]
                            except Exception as ej:
                                print(f"       [Erro ao atualizar JSON na reconciliação]: {ej}")

                        if os.path.exists(JOURNAL_CSV):
                            try:
                                rows = []
                                with open(JOURNAL_CSV, "r", newline="", encoding="utf-8") as f:
                                    reader = csv.reader(f)
                                    for r in reader:
                                        if len(r) > 17 and r[1] == str(cycle_num):
                                            r[14] = official_winner
                                            r[15] = new_res_str
                                            r[16] = str(new_total_payout)
                                            r[17] = str(new_cycle_pnl)
                                            r[19] = str(round(real_bal, 2))
                                        rows.append(r)
                                tmp_csv = JOURNAL_CSV + ".tmp"
                                with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
                                    writer = csv.writer(f)
                                    writer.writerows(rows)
                                    f.flush()
                                    os.fsync(f.fileno())
                                os.replace(tmp_csv, JOURNAL_CSV)
                            except Exception as ec:
                                print(f"       [Erro ao atualizar CSV na reconciliação]: {ec}")

                    print(f"       -> Reconciliação concluída! Resultado corrigido para: {new_res_str} | Saldo real: ${real_bal:.2f} USDC\n")
                else:
                    # Oráculo oficial confirmou o resultado provisório.
                    # Atualiza o saldo real em carteira pós-liquidação do payout pelo contrato da Polymarket
                    time.sleep(2.0)
                    real_bal = self.get_usdc_balance()
                    with self.journal_lock:
                        if os.path.exists(JOURNAL_JSON):
                            try:
                                with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                                    jdata = json.load(f)
                                for t in jdata.get("trades", []):
                                    if t.get("cycle") == cycle_num:
                                        t["winner_source"] = "POLYMARKET_OFFICIAL"
                                        t["balance"] = real_bal
                                        break
                                jdata["current_balance"] = real_bal
                                jdata["session_pnl"] = round(real_bal - jdata.get("session_initial_balance", real_bal), 2)
                                jdata["total_pnl_vs_deposit"] = round(real_bal - self.initial_deposit, 2)
                                _atomic_json_write(JOURNAL_JSON, jdata)
                                self.current_balance = real_bal
                                self.session_pnl = jdata["session_pnl"]
                            except Exception as ej:
                                print(f"       [Erro ao atualizar JSON na confirmação]: {ej}")

                        if os.path.exists(JOURNAL_CSV):
                            try:
                                rows = []
                                with open(JOURNAL_CSV, "r", newline="", encoding="utf-8") as f:
                                    reader = csv.reader(f)
                                    for r in reader:
                                        if len(r) > 19 and r[1] == str(cycle_num):
                                            r[19] = str(round(real_bal, 2))
                                        rows.append(r)
                                tmp_csv = JOURNAL_CSV + ".tmp"
                                with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
                                    writer = csv.writer(f)
                                    writer.writerows(rows)
                                    f.flush()
                                    os.fsync(f.fileno())
                                os.replace(tmp_csv, JOURNAL_CSV)
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
            real_tok = self.get_token_balance(target_token) if self.execution_mode != "paper" else shares
            raw_s = real_tok if real_tok > 0 else shares
            sell_shares = int(raw_s * 100) / 100.0
            if sell_shares >= 0.1:
                print(f"    [🚨 STOP-LOSS DE EMERGENCIA]: Ha liquidez para estancar a perda! Best Bid de {target_side}: ${best_bid_primary:.2f} (>= ${STOP_LOSS_MIN_BID:.2f}).")
                print(f"       Vendendo {sell_shares:.2f} cotas de {target_side} a mercado para resgatar caixa...")
                sl_res = self.place_live_order(target_token, "SELL", sell_shares, price=best_bid_primary)
                if sl_res and sl_res.get("status") == "SUCCESS":
                    sl_confirmed = True
                    if self.execution_mode != "paper":
                        time.sleep(1.5)
                        rem_tok = self.get_token_balance(target_token)
                        if rem_tok >= sell_shares:
                            print(f"       [ALERTA STOP-LOSS] Ordem aceita pela API mas cotas continuam na carteira ({rem_tok:.2f} cotas). FAK não preenchido.")
                            sl_confirmed = False

                    if sl_confirmed:
                        s_resp = sl_res.get("response", {})
                        s_hashes = s_resp.get("transactionsHashes") or []
                        early_tx = s_hashes[0] if s_hashes else (s_resp.get("orderID") or "EXECUTED")
                        early_payout = round(sell_shares * best_bid_primary, 2)
                        print(f"       -> STOP-LOSS EXECUTADO COM SUCESSO! Tx: {early_tx}")
                        print(f"       -> Saldo resgatado da posicao: ${early_payout:.2f} USDC (Perda estancada em -${(1.00 - early_payout):.2f})")
                        return {
                            "success": True,
                            "tx_hash": early_tx,
                            "price": best_bid_primary,
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

    def place_live_order(self, token_id: str, side: str, amount: float, price: Optional[float] = None, max_price: Optional[float] = None) -> Dict[str, Any]:
        """Cria e envia ordem a mercado real para o Polymarket CLOB V2 (BUY em USDC, SELL em cotas)"""
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

        # 0. Verificacao de Geoblock em Tempo Real
        geo = check_geoblock()
        if geo.get("blocked", False):
            print(f"\n[GEOBLOCK BLOQUEADO]: IP {geo.get('ip')} ({geo.get('country')}) esta bloqueado para ordens!")
            print("   Certifique-se de que a NordVPN esta conectada a Portugal e aguarde...")
            time.sleep(15)
            return

        # 1. Verifica limites do Circuit Breaker na Sessao Ativa
        if self.session_pnl <= MAX_LOSS_LIMIT:
            self.is_halted = True
            self.halt_reason = f"STOP LOSS DE SESSAO ATINGIDO (P&L: ${self.session_pnl:.2f} <= ${MAX_LOSS_LIMIT:.2f}). Protecao de capital ativada."
            print(f"\n[CIRCUIT BREAKER]: {self.halt_reason}")
            return

        if self.session_pnl >= TAKE_PROFIT_LIMIT:
            self.is_halted = True
            self.halt_reason = f"TAKE PROFIT DE SESSAO ATINGIDO (P&L: ${self.session_pnl:.2f} >= ${TAKE_PROFIT_LIMIT:.2f}). Lucro garantido com sucesso!"
            print(f"\n[CIRCUIT BREAKER]: {self.halt_reason}")
            return

        # 2. Verifica Saldo Disponivel
        bal = self.get_usdc_balance()
        if bal < 0:
            print("    [!] Falha de comunicacao ao consultar saldo USDC na Polygon. Pulando rodada por seguranca.")
            time.sleep(15)
            return
        print(f"    Saldo Real em Carteira: ${bal:.2f} USDC")
        if bal < FIXED_STAKE:
            print(f"    [!] Saldo insuficiente para aposta de ${FIXED_STAKE:.2f} USDC.")
            print(f"    -> Aguardando saldo... (Pressione Ctrl+C para sair)")
            time.sleep(15)
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
            if strike:
                self.candle_strikes[window_ts] = strike
            else:
                strike = get_candle_open(window_ts) or 0.0

        if window_ts in self.binance_opens:
            binance_open = self.binance_opens[window_ts]
        else:
            binance_open = get_candle_open(window_ts) or get_binance_spot() or strike
            if binance_open:
                self.binance_opens[window_ts] = binance_open

        binance_spot = get_binance_spot() or binance_open
        feed_diff = binance_spot - strike if strike else 0.0
        print(f"    Strike Oraculo Chainlink (K): ${strike:,.2f} | Binance Ref: ${binance_spot:,.2f} (Spread: ${feed_diff:+.2f})")

        # 4. Aguarda ate o segundo 135 para a tomada de decisao estatistica
        eval_sec = 135
        if seconds_elapsed < eval_sec:
            wait_time = eval_sec - seconds_elapsed
            print(f"    Monitorando microestrutura via Chainlink... aguardando {wait_time}s ate o minuto 2:15")
            time.sleep(wait_time)

        # 5. Analise de Drift e Sinal via Oraculo Chainlink
        spot_eval = get_chainlink_price() or strike
        delta = spot_eval - strike
        binance_eval = get_binance_spot() or spot_eval
        spread_eval = binance_eval - spot_eval
        binance_drift = binance_eval - binance_open
        print(f"    Spot Chainlink aos 135s: ${spot_eval:,.2f} | Drift Real (Delta): ${delta:+.2f}")
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

        if delta >= 18.0:
            target_side = "UP"
            target_token = token_up
            estimated_price = price_up
            rationale = f"Drift Positivo Chainlink (+${delta:.1f} acima do strike)"
            should_trade_primary = True
        elif delta <= -18.0:
            target_side = "DOWN"
            target_token = token_down
            estimated_price = price_down
            rationale = f"Drift Negativo Chainlink (-${abs(delta):.1f} abaixo do strike)"
            should_trade_primary = True
        else:
            # REGRA 1 (Deadband): Ruido (|Delta| < $18.00). Nao forcar aposta primaria no meio do caminho!
            print(f"\n    [🛡️ FILTRO DE RUIDO DEADBAND]: Delta de ${delta:+.2f} esta dentro da zona morta (< $18.00).")
            print("       -> Preservando capital! Nenhuma aposta primaria forcada no ruido.")
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

        if strike_captured_late and should_trade_primary:
            print(f"\n    [🛡️ FILTRO TEMPO]: Strike K amostrado com atraso (>20s). Entrada primaria cancelada para evitar delta contaminado.")
            should_trade_primary = False

        if should_trade_primary and self._is_past_deadline(window_ts, 295):
            print(f"\n    [🛡️ FILTRO DEADLINE]: Tempo decorrido (>295s) proximo ao fechamento. Entrada primaria abortada.")
            should_trade_primary = False

        # 6. Execucao da Ordem Real Primaria (se aprovada pelos filtros)
        has_primary = False
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

                # MELHORIA 1: Filtro de Spread do Order Book (Spread > 0.06 = iliquidez tóxica / slippage)
                if spread > 0.06:
                    print(f"       [🛡️ FILTRO DE SPREAD CLOB]: Spread ${spread:.3f} > $0.060 (Livro Iliquido).")
                    print("       -> Preservando capital! Entrada cancelada devido ao risco de slippage tóxico.")
                    should_trade_primary = False

                # MELHORIA 2: Filtro de Desbalanceamento do Order Book (Ask Wall Confirmation)
                elif top_imb < -0.25 and depth_imb < -0.20:
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
                    print(f"    [🛡️ FILTRO DE PRECO SNIPER]: Preco ${estimated_price:.2f} > ${PRIMARY_MAX_PRICE:.2f} (Breakeven desfavoravel > 60%). Pulando entrada primaria.")
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

            # REGRA 4: Filtro de CVD Tick Data (Anti-Armadilha de Absorção Institucional)
            if should_trade_primary and not is_streak_snapper:
                cvd_stats = self.cvd_watcher.get_window_cvd(window_seconds=135)
                print(f"\n    [🌊 FLUXO DE CVD - CUMULATIVE VOLUME DELTA]:")
                print(f"       Net CVD: ${cvd_stats['net_cvd_usd']/1e6:+.2f}M | Ratio Compra: {cvd_stats['cvd_ratio']*100:.1f}% | Sinal: {cvd_stats['dominant_signal']} ({cvd_stats['source']})")
                if target_side == "UP" and cvd_stats["dominant_signal"] == "DOWN":
                    print(f"       [🛡️ FILTRO CVD]: Absorção detectada! Preço subindo, mas agressão institucional é de VENDA (${cvd_stats['net_cvd_usd']/1e6:+.2f}M).")
                    print("       -> Preservando capital! Abortando entrada primária para evitar Bull Trap.")
                    should_trade_primary = False
                elif target_side == "DOWN" and cvd_stats["dominant_signal"] == "UP":
                    print(f"       [🛡️ FILTRO CVD]: Absorção detectada! Preço caindo, mas agressão institucional é de COMPRA (${cvd_stats['net_cvd_usd']/1e6:+.2f}M).")
                    print("       -> Preservando capital! Abortando entrada primária para evitar Bear Trap.")
                    should_trade_primary = False
                elif cvd_stats["dominant_signal"] == target_side:
                    print(f"       [🔥 ALTA CONVICÇÃO CVD]: Fluxo de agressão institucional alinhado com {target_side}!")
                    rationale += f" + Convicção CVD ({cvd_stats['dominant_signal']})"

        if should_trade_primary:
            print(f"\n    [ENTRADA QUANTITATIVA]: {target_side} | Preco Real (Microprice): ${estimated_price:.2f}")
            print(f"       Racional: {rationale}")
            print(f"       Enviando ordem de ${FIXED_STAKE:.2f} USDC para a CLOB V2...")
            limit_p = min(PRIMARY_MAX_PRICE, round(estimated_price + 0.01, 2))
            order_res = self.place_live_order(target_token, "BUY", FIXED_STAKE, price=limit_p, max_price=PRIMARY_MAX_PRICE)
            print(f"       Resultado do Envio Primário: {order_res.get('status')}")
            if order_res.get("status") == "SUCCESS":
                resp_data = order_res.get("response", {})
                order_id = resp_data.get("orderID") or "EXECUTED"
                tx_hashes = resp_data.get("transactionsHashes") or []
                tx_hash = tx_hashes[0] if tx_hashes else ""

                if self.execution_mode == "paper":
                    has_primary = True
                    shares = round(FIXED_STAKE / max(0.01, estimated_price), 4)
                    print(f"       -> [MODO PAPER] ORDEM PRIMÁRIA SIMULADA! ID: {order_id} | {shares:.4f} cotas @ ${estimated_price:.2f}")
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

            current_chainlink = get_chainlink_price()
            if current_chainlink:
                last_candle_chainlink = current_chainlink
                current_delta = current_chainlink - strike

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
                            min_tp_price = min(min_tp_price, max(0.72, round(estimated_price * 1.40, 2)))

                        # 3. Se tempo avançado (elapsed >= 225s), garante lucro sólido antes dos segundos finais
                        if elapsed >= 225 and cur_bid >= 0.78 and cur_bid >= round(estimated_price * 1.25, 2):
                            min_tp_price = min(min_tp_price, cur_bid)

                        if cur_bid >= min_tp_price and bid_size >= 1.0:
                            print(f"\n    [💰 SIRMARTINGALE TAKE-PROFIT!] Aos {elapsed}s: CLOB Best Bid atingiu ${cur_bid:.2f} (>= ${min_tp_price:.2f}, entrada: ${estimated_price:.2f})!")
                            real_tok = self.get_token_balance(target_token) if self.execution_mode != "paper" else shares
                            raw_s = real_tok if real_tok > 0 else shares
                            sell_shares = int(raw_s * 100) / 100.0
                            sell_res = None
                            if sell_shares >= 0.1 and not self._is_past_deadline(window_ts, 295):
                                print(f"       Vendendo {sell_shares:.2f} cotas na CLOB para travar lucro garantido (~+{((cur_bid/max(0.01, estimated_price)-1)*100):.0f}%)...")
                                sell_res = self.place_live_order(target_token, "SELL", sell_shares, price=cur_bid)
                            if sell_res and sell_res.get("status") == "SUCCESS":
                                sell_confirmed = True
                                if self.execution_mode != "paper":
                                    time.sleep(1.5)
                                    rem_tok = self.get_token_balance(target_token)
                                    if rem_tok >= sell_shares:
                                        print(f"       [ALERTA TAKE-PROFIT] Ordem aceita pela API mas cotas continuam na carteira ({rem_tok:.2f} cotas). FAK não preenchido.")
                                        sell_confirmed = False

                                if sell_confirmed:
                                    sold_early = True
                                    has_primary = False
                                    s_resp = sell_res.get("response", {})
                                    s_hashes = s_resp.get("transactionsHashes") or []
                                    early_sell_tx_hash = s_hashes[0] if s_hashes else (s_resp.get("orderID") or "EXECUTED")
                                    early_sell_price = cur_bid
                                    early_sell_payout = round(sell_shares * cur_bid, 2)
                                    print(f"       -> VENDA ANTECIPADA EXECUTADA! Tx: {early_sell_tx_hash} | Payout Travado: ${early_sell_payout:.2f} USDC")
                                else:
                                    print("       -> Venda antecipada não consumada no livro. Posição mantida aberta para próxima tentativa.")
                            else:
                                print(f"       [Falha na venda antecipada]: {sell_res.get('error') if sell_res else 'Saldo insuficiente ou deadline excedido'}")

                # --- DEFESA: Bonereaper Hedge Dinamico e Evaporação de Drift ---
                reversal = False
                evaporation = False
                if has_primary and not sold_early:
                    cur_b_spot = get_binance_spot() or current_chainlink
                    b_open = self.binance_opens.get(window_ts, strike)
                    b_drift = (cur_b_spot - b_open) if (cur_b_spot and b_open) else current_delta
                    
                    # 1. Reversão contra o strike
                    if target_side == "UP":
                        if current_delta <= -HEDGE_DELTA_THRESHOLD or (current_delta < -2.0 and b_drift < -5.0):
                            reversal = True
                    elif target_side == "DOWN":
                        if current_delta >= HEDGE_DELTA_THRESHOLD or (current_delta > 2.0 and b_drift > 5.0):
                            reversal = True

                    # 2. Evaporação de Drift (Lição Ciclo 116: perda de >85% da borda inicial)
                    if not reversal and elapsed >= 180 and abs(entry_delta) >= 25.0:
                        if target_side == "UP" and current_delta <= 2.50:
                            evaporation = True
                        elif target_side == "DOWN" and current_delta >= -2.50:
                            evaporation = True

                # Trata evaporação de borda preventivamente via Stop-Loss
                if evaporation and not sold_early and not hedged:
                    print(f"\n    [⚠️ EVAPORAÇÃO DE DRIFT DETECTADA!] Aos {elapsed}s:")
                    print(f"       Delta inicial foi ${entry_delta:+.2f}, mas desabou para ${current_delta:+.2f} (perda de margem de segurança).")
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
                                    print(f"       [AVISO HEDGE] Ordem enviada mas cota de hedge nao preenchida (FAK). Acionando Stop-Loss de emergencia...")
                                    sl_data = self._execute_emergency_stop_loss(target_token, target_side, shares, window_ts)
                                    if sl_data["success"]:
                                        sold_early = True
                                        has_primary = False
                                        early_sell_tx_hash = sl_data["tx_hash"]
                                        early_sell_price = sl_data["price"]
                                        early_sell_payout = sl_data["payout"]
                        else:
                            print(f"       [Falha no hedge]: {hedge_res.get('error')}. Acionando Stop-Loss de emergencia...")
                            sl_data = self._execute_emergency_stop_loss(target_token, target_side, shares, window_ts)
                            if sl_data["success"]:
                                sold_early = True
                                has_primary = False
                                early_sell_tx_hash = sl_data["tx_hash"]
                                early_sell_price = sl_data["price"]
                                early_sell_payout = sl_data["payout"]
                    else:
                        if hedge_best_ask > HEDGE_MAX_PRICE:
                            print(f"    [🛡️ HEDGE RECUSADO - EV NEGATIVO]: Preco de {hedge_side} esta em ${hedge_best_ask:.2f} (> ${HEDGE_MAX_PRICE:.2f}).")
                            print("       Comprar a ponta oposta no topo garante prejuizo certo ($1.00 gasto para < $1.00 retorno).")
                        elif cur_bal < HEDGE_STAKE:
                            print(f"       [Aviso Hedge] Saldo insuficiente (${cur_bal:.2f}) para hedge de ${HEDGE_STAKE:.2f}")

                        # PROTOCOLO DE STOP-LOSS ANTECIPADO: Vender cotas da posicao perdedora na CLOB
                        sl_data = self._execute_emergency_stop_loss(target_token, target_side, shares, window_ts)
                        if sl_data["success"]:
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

        # Se ainda nao liquidou na API, usa o fechamento intra-vela da Chainlink como apuracao provisoria
        final_chainlink = last_candle_chainlink or get_chainlink_price() or spot_eval
        final_delta = final_chainlink - strike
        chainlink_winner = "UP" if final_chainlink >= strike else "DOWN"

        if official_winner:
            winner = official_winner
            winner_source = "POLYMARKET_OFFICIAL"
        else:
            winner = chainlink_winner
            winner_source = "CHAINLINK_ORACLE (PROVISORIO)"

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
            total_stake += FIXED_STAKE
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

        # Aguarda brevemente para refletir saldo no relayer
        if total_payout > 0 and self.execution_mode != "paper":
            time.sleep(3.0)
        new_balance = self.get_usdc_balance()
        if new_balance < 0:
            new_balance = self.current_balance

        # Atualizacao do P&L Real da Sessao e vs Deposito
        self.session_pnl = round(new_balance - self.session_initial_balance, 2)
        total_pnl_vs_deposit = round(new_balance - self.initial_deposit, 2)

        # Verificacao de paridade contabil carteira Polygon vs Sessao (sem reset forçado)
        if self.execution_mode != "paper":
            expected_journal_balance = round(self.session_initial_balance + self.session_pnl, 2)
            parity_gap = abs(new_balance - expected_journal_balance)
            if parity_gap > 2.00:
                print(f"\n    [⚠️ ALERTA DE PARIDADE CONTÁBIL]: Divergência de ${parity_gap:.2f} detectada entre saldo real (${new_balance:.2f}) e diário (${expected_journal_balance:.2f}).")
                print("       Preservando contabilidade real da sessão e Circuit Breakers (sem reset forçado).")

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
            with open(JOURNAL_CSV, "a", newline="", encoding="utf-8") as f:
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
                "mode": "LIVE_TRADING_V2_CHAINLINK_BONEREAPER_SIRMARTINGALE_SCOUR",
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
                "last_updated": datetime.now().isoformat(),
                "trades": []
            }
            if os.path.exists(JOURNAL_JSON):
                try:
                    with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                        prev = json.load(f)
                        json_data["trades"] = prev.get("trades", [])
                except Exception:
                    pass
            json_data["trades"].append(trade_entry)
            _atomic_json_write(JOURNAL_JSON, json_data)

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
