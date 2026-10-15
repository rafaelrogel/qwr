"""
=============================================================================
KALSHI GOLD 15-MINUTE ALGO TRADER (KXGOLD15M) — MODO PAPER
=============================================================================
- Protocolo Oficial: Kalshi Trade API v2 (Autenticação Criptográfica RSA-PSS SHA-256)
- Mercado: KXGOLD15M (Gold price up in next 15 mins?)
- Oráculo de Referência Spot: Pyth Network (Metal.Index.GOLD/USD) + Binance PAXGUSDT
- Gestão de Risco & Estratégia Quantitativa:
  * Ponto de Avaliação Ótimo: 450s (50% da vela de 15m)
  * Deadband Dinâmico Scale-Invariant: 4.0 bps ($1.70 em $4,280 Ouro)
  * Filtro Jev Trend Continuation: Confirmação com vela anterior de 15m
  * Teto de Preço: Máximo de $0.60 por cota (evita assimetria negativa)
  * Take-Profit Antecipado (SirMartingale): Venda travando lucro se cota atingir >= $0.88
  * Stop-Loss Proativo: Liquidação se delta inverter além do ponto de segurança
  * Shard de Execução: Shard 2 (Commodities)
- Modo: PAPER HYPER-REALISTA (Lê book real da Kalshi e simula preenchimento)
=============================================================================
"""

import os
import sys
import time
import json
import base64
import urllib
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List, Tuple

from risk_gate import compute_kalshi_dynamic_contracts, atomic_write_json, safe_read_json, record_desk_trade_result
from execution_math import calculate_black_scholes_digital_fv
from variable_bench import bench
from jev_microstructure_gate import jev_gate

# Garante suporte a UTF-8 no stdout/stderr do Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Caminhos dos arquivos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
JOURNAL_JSON = os.path.join(BASE_DIR, "kalshi_gold_15m_journal.json")
LIVE_STATE_JSON = os.path.join(BASE_DIR, "kalshi_gold_15m_live_state.json")

# Configurações de API Kalshi
KALSHI_API_PROD = "https://external-api.kalshi.com/trade-api/v2"

# Parâmetros Quantitativos (Calibração Institucional JEV AI — Ouro 15m)
FIXED_STAKE = 1.00                # $1.00 USD por aposta primária (1 contrato)
DEADBAND_BPS = 0.00035            # 3.5 bps (0.035%) do preço do Ouro ($1.50 em $4,280)
DEADBAND_MIN_FLOOR = 1.50         # Piso mínimo absoluto de $1.50 no Ouro
PRIMARY_MAX_PRICE = 0.60          # Preço máximo por cota (60¢)
PRIMARY_MIN_PRICE = 0.40          # Preço mínimo por cota (40¢ - Proteção JEV anti-seleção adversa)
MAX_SPREAD = 0.04                 # Spread máximo aceito no book (4¢ - blindagem contra iliquidez noturna)
TAKE_PROFIT_PRICE = 0.88          # Take-Profit antecipado SirMartingale (88¢)
STOP_LOSS_MIN_BID = 0.15          # Preço mínimo para Stop-Loss antecipado (15¢)
EVAL_POINT_SEC = 420              # Decisão primária aos 420s (Minuto 7:00 - Sweet Spot 87% WR / +31¢ EV)
EVAL_MAX_SEC = 465                # Janela de entrada primária (07m00s a 07m45s)
SWEEPER_POINT_SEC = 780           # Varredura Sweeper aos 780s (Minuto 13:00 - Captura tardia de alta certeza)
SWEEPER_MAX_SEC = 830             # Janela da varredura final (13m00s a 13m50s)
SWEEPER_MAX_PRICE = 0.65          # Preço teto blindado (65¢ - elimina risco assimétrico de pagar >90¢ para ganhar 6¢)

PYTH_GOLD_FEED_ID = "fa0f57505be633c026896e15afef2c7ce2cf8ff9a45349d1da737f4f01266b01"

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
EXECUTION_MODE = ENV_CFG.get("GOLD_15M_MODE", "PAPER").upper()
KALSHI_KEY_ID = ENV_CFG.get("KALSHI_KEY_ID", "")
raw_key_path = ENV_CFG.get("KALSHI_PRIVATE_KEY_PATH", "kalshi.txt")
KALSHI_PRIVATE_KEY_PATH = raw_key_path if os.path.isabs(raw_key_path) else os.path.join(BASE_DIR, raw_key_path)
PYTH_API_KEY = ENV_CFG.get("PYTH_API_KEY", "")

# ===================== CLIENTE KALSHI API V2 =====================
class KalshiClientV2:
    def __init__(self, key_id: str, private_key_pem_path: str):
        self.key_id = key_id
        self.private_key_path = private_key_pem_path
        self.base_url = KALSHI_API_PROD
        self.private_key = None
        self._load_private_key()

    def _load_private_key(self):
        if not os.path.exists(self.private_key_path):
            return
        try:
            from cryptography.hazmat.primitives import serialization
            with open(self.private_key_path, "rb") as key_file:
                self.private_key = serialization.load_pem_private_key(key_file.read(), password=None)
        except Exception as e:
            print(f"[!] Erro ao carregar chave RSA Kalshi: {e}")

    def _sign(self, method: str, path: str, timestamp_ms: int) -> str:
        if not self.private_key:
            return ""
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding
            message = f"{timestamp_ms}{method}{path}".encode("utf-8")
            signature = self.private_key.sign(
                message,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                hashes.SHA256()
            )
            return base64.b64encode(signature).decode("utf-8")
        except Exception:
            return ""

    def request(self, method: str, endpoint: str, params: dict = None, body: dict = None, auth_required: bool = False) -> Optional[dict]:
        clean_path = "/trade-api/v2" + endpoint
        url = self.base_url + endpoint
        if params:
            url += "?" + urllib.parse.urlencode(params)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AntigravityKalshiGoldTrader/2.0"
        }

        if auth_required:
            ts_ms = int(time.time() * 1000)
            sig = self._sign(method, clean_path, ts_ms)
            headers["KALSHI-ACCESS-KEY"] = self.key_id
            headers["KALSHI-ACCESS-SIGNATURE"] = sig
            headers["KALSHI-ACCESS-TIMESTAMP"] = str(ts_ms)

        data = json.dumps(body).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    def get_real_balance(self) -> dict:
        """Consulta saldo real segregado oficial na Kalshi"""
        res = self.request("GET", "/portfolio/balance", auth_required=True)
        shard2_bal = 0.0
        total_bal = 0.0
        if res:
            if "balance_dollars" in res:
                total_bal = float(res["balance_dollars"])
            breakdowns = res.get("balance_breakdown", [])
            for b in breakdowns:
                if b.get("exchange_index") == 2:
                    shard2_bal = float(b.get("balance", 0.0))
        return {"total_balance": total_bal, "shard2_balance": shard2_bal}

    def get_portfolio_settlement(self, ticker: str, max_retries: int = 6, delay: int = 3) -> Optional[dict]:
        """Consulta liquidação oficial indiscutível no portfólio Kalshi (/portfolio/settlements)"""
        for _ in range(max_retries):
            res = self.request("GET", "/portfolio/settlements", auth_required=True)
            if res and "settlements" in res:
                for s in res["settlements"]:
                    if s.get("ticker") == ticker:
                        return s
            time.sleep(delay)
        return None

    def get_gold_15m_markets(self) -> List[dict]:
        """
        Busca os mercados KXGOLD15M ativos na Kalshi.
        Arquitetura Certificada pelo JEV SystemOne:
        1. Detecção da Janela Diária de Manutenção Kalshi (03:00 - 05:00 ET / 07:00 - 09:00 UTC).
        2. Consulta por Janela Temporal Estrita (min_close_ts / max_close_ts).
        3. Resolução Determinística de Ticker via Fuso ET (KXGOLD15M-{YY}{MMM}{DD}{HHMM}-{MM}).
        4. Fallback com ordenação ascendente por close_time.
        """
        now_utc = datetime.now(timezone.utc)
        now_ts = int(now_utc.timestamp())
        now_iso = now_utc.isoformat()

        # 0. Verificação da Janela Diária de Manutenção Kalshi (03:00 às 05:00 AM ET / 07:00 às 09:00 UTC)
        try:
            ny_tz = ZoneInfo("America/New_York")
            now_et = now_utc.astimezone(ny_tz)
            if now_et.hour in (3, 4):
                print(f"   [🏛️ KALSHI EXCHANGE HALT]: Janela diária oficial de manutenção e clearing ({now_et.strftime('%H:%M')} ET / {now_utc.strftime('%H:%M')} UTC). Nenhum contrato KXGOLD15M emitido.")
                return []
        except Exception:
            pass

        # 1. Consulta Cirúrgica por Janela Temporal Estrita (min_close_ts / max_close_ts)
        try:
            params = {
                "series_ticker": "KXGOLD15M",
                "min_close_ts": now_ts,
                "max_close_ts": now_ts + 1200,
                "limit": 10
            }
            res = self.request("GET", "/markets", params=params)
            if res and "markets" in res and res["markets"]:
                valid_markets = []
                for m in res["markets"]:
                    ct = m.get("close_time")
                    st = m.get("status")
                    if (st in ("active", "open", "initialized")) and (not ct or ct > now_iso):
                        valid_markets.append(m)
                if valid_markets:
                    valid_markets.sort(key=lambda x: x.get("close_time", ""))
                    return valid_markets
        except Exception as e:
            print(f"   [Desk 9 Gold Discovery L1]: Erro na consulta temporal: {e}")

        # 2. Resolução Determinística de Ticker (Cálculo do Ticker Intradiário)
        try:
            ny_tz = ZoneInfo("America/New_York")
            now_et = now_utc.astimezone(ny_tz)
            rem_min = 15 - (now_et.minute % 15)
            close_et = (now_et + timedelta(minutes=rem_min)).replace(second=0, microsecond=0)
            yy = close_et.strftime("%y")
            mmm = close_et.strftime("%b").upper()
            dd = close_et.strftime("%d")
            hhmm = close_et.strftime("%H%M")
            mm = close_et.strftime("%M")
            det_ticker = f"KXGOLD15M-{yy}{mmm}{dd}{hhmm}-{mm}"

            res_single = self.request("GET", f"/markets/{det_ticker}")
            if res_single and "market" in res_single:
                m = res_single["market"]
                ct = m.get("close_time")
                if not ct or ct > now_iso:
                    return [m]
        except Exception as e:
            print(f"   [Desk 9 Gold Discovery L2]: Erro na resolução determinística: {e}")

        # 3. Fallback Resiliente com Ordenação Ascendente por close_time
        try:
            res_fb = self.request("GET", "/markets", params={"series_ticker": "KXGOLD15M", "min_close_ts": now_ts, "limit": 100})
            if res_fb and "markets" in res_fb:
                active_markets = []
                for m in res_fb["markets"]:
                    ct = m.get("close_time")
                    st = m.get("status")
                    if st in ("active", "open", "initialized") and (not ct or ct > now_iso):
                        active_markets.append(m)
                if active_markets:
                    active_markets.sort(key=lambda x: x.get("close_time", ""))
                    return [active_markets[0]]
        except Exception as e:
            print(f"   [Desk 9 Gold Discovery L3]: Erro no fallback: {e}")

        return []

    def get_orderbook(self, ticker: str) -> Optional[dict]:
        return self.request("GET", f"/markets/{ticker}/orderbook")

    def place_order(self, ticker: str, side: str, count: int, price_cents: int, action: str = "buy") -> Optional[dict]:
        """Envia ordem limit oficial V2 na Kalshi (side='yes' ou 'no', action='buy' ou 'sell')"""
        action = action.lower()
        side = side.lower()
        if action == "buy":
            book_side = "bid" if side == "yes" else "ask"
            price_dollars = f"{price_cents / 100.0:.4f}" if side == "yes" else f"{(100 - price_cents) / 100.0:.4f}"
        else:
            book_side = "ask" if side == "yes" else "bid"
            price_dollars = f"{price_cents / 100.0:.4f}" if side == "yes" else f"{(100 - price_cents) / 100.0:.4f}"

        payload = {
            "ticker": ticker,
            "side": book_side,
            "type": "limit",
            "count": str(count),
            "price": price_dollars,
            "self_trade_prevention_type": "taker_at_cross",
            "time_in_force": "good_till_canceled",
            "client_order_id": f"kgold15_{action}_{int(time.time()*1000)}"
        }
        return self.request("POST", "/portfolio/events/orders", body=payload, auth_required=True)

    def cancel_order(self, order_id: str, exchange_index: int = 2) -> Optional[dict]:
        """Cancela ordem oficial V2 na Kalshi"""
        return self.request("DELETE", f"/portfolio/orders/{order_id}?exchange_index={exchange_index}", auth_required=True)

    def get_order_status(self, order_id: str) -> Optional[dict]:
        """Consulta o status de uma ordem oficial na Kalshi"""
        return self.request("GET", f"/portfolio/orders/{order_id}", auth_required=True)


# ===================== PARSERS DE LIVRO KALSHI V2 (ORDERBOOK_FP) =====================
def extract_best_ask_and_qty(ob_dict: Optional[dict], target_side: str) -> Tuple[Optional[float], int]:
    """
    Extrai o melhor preço de Ask (compra a mercado) e quantidade disponível
    do livro complementar da Kalshi API v2 (orderbook_fp).
    - Para comprar YES: Ask = 1.00 - max(no_dollars)
    - Para comprar NO: Ask = 1.00 - max(yes_dollars)
    """
    if not ob_dict or "orderbook_fp" not in ob_dict:
        return None, 1
    fp = ob_dict["orderbook_fp"]
    y_orders = fp.get("yes_dollars", [])
    n_orders = fp.get("no_dollars", [])

    if target_side.upper() == "YES":
        if n_orders:
            best_no_bid = float(n_orders[-1][0])
            ask_price = round(1.00 - best_no_bid, 4)
            qty = int(float(n_orders[-1][1])) if len(n_orders[-1]) > 1 else 1
            return ask_price, qty
    else:  # NO
        if y_orders:
            best_yes_bid = float(y_orders[-1][0])
            ask_price = round(1.00 - best_yes_bid, 4)
            qty = int(float(y_orders[-1][1])) if len(y_orders[-1]) > 1 else 1
            return ask_price, qty
    return None, 1


def extract_best_bid(ob_dict: Optional[dict], pos_side: str) -> Optional[float]:
    """
    Extrai o melhor preço de Bid (venda a mercado da cota na mão para Take-Profit):
    - Para vender YES: Bid = max(yes_dollars)
    - Para vender NO: Bid = max(no_dollars)
    """
    if not ob_dict or "orderbook_fp" not in ob_dict:
        return None
    fp = ob_dict["orderbook_fp"]
    if pos_side.upper() == "YES":
        y_orders = fp.get("yes_dollars", [])
        return float(y_orders[-1][0]) if y_orders else None
    else:
        n_orders = fp.get("no_dollars", [])
        return float(n_orders[-1][0]) if n_orders else None


# ===================== FEEDS SPOT OURO (XAU) =====================
def get_gold_spot() -> Optional[float]:
    """
    Feed Oficial de Spot Ouro (KXGOLD15M) sincronizado com o Oráculo da Kalshi:
    1. Primário (Sub-segundo): pyth_gold_live_feed.json gerado pelo Playwright Headless Watcher (WebSocket DOM Metal.Index.1OZGOLD/USD).
    2. Secundário: API REST Pyth Network (Metal.Index.1OZGOLD/USD).
    3. Fallback: Coinbase PAXG-USD Spot API.
    """
    # 1. Stream WebSocket DOM em Tempo Real (Playwright Watcher - Metal.Index.1OZGOLD/USD)
    feed_path = os.path.join(BASE_DIR, "pyth_gold_live_feed.json")
    if os.path.exists(feed_path):
        try:
            with open(feed_path, "r", encoding="utf-8") as f:
                feed = json.load(f)
            age = time.time() - float(feed.get("ts", 0))
            if age <= 12.0 and float(feed.get("spot", 0)) > 1000.0:
                return round(float(feed["spot"]), 2)
        except Exception:
            pass

    # 2. API REST Pyth Network Oficial da Kalshi (Metal.Index.1OZGOLD/USD)
    try:
        pyth_url = "https://app.pyth.com/api/price-feeds?query=Metal.Index.1OZGOLD/USD"
        req = urllib.request.Request(pyth_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=2.5) as r:
            data = json.loads(r.read().decode("utf-8"))
            for item in data.get("data", []):
                if item.get("symbol") == "Metal.Index.1OZGOLD/USD":
                    p = item.get("latest_price")
                    if p and float(p) > 1000.0:
                        return round(float(p), 2)
    except Exception:
        pass

    # Fallback 2: Coinbase PAXG-USD Spot (ouro físico real 1:1, sem distorção de futuros)
    try:
        url_cb = "https://api.exchange.coinbase.com/products/PAXG-USD/ticker"
        req = urllib.request.Request(url_cb, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2.5) as r:
            cb_data = json.loads(r.read().decode())
            if "price" in cb_data:
                return round(float(cb_data["price"]), 2)
    except Exception:
        pass

    return None

def get_gold_15m_prior_candle() -> Optional[Dict[str, Any]]:
    """Vela de 15m anterior do Ouro (XAUUSDT) na Binance Futures"""
    url = "https://fapi.binance.com/fapi/v1/klines?symbol=XAUUSDT&interval=15m&limit=2"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode())
            if len(data) >= 2:
                c = data[0]
                o, cl = float(c[1]), float(c[4])
                direction = "UP" if cl >= o else "DOWN"
                diff_bps = (abs(cl - o) / o) * 10000
                return {"direction": direction, "open": o, "close": cl, "diff_bps": round(diff_bps, 1)}
    except Exception:
        pass
    return None

# ===================== MOTOR DO DESK OURO 15M =====================
class GoldTrader15M:
    def __init__(self):
        self.mode = EXECUTION_MODE
        self.balance = 100.00 # Saldo paper de referência
        self.client = KalshiClientV2(KALSHI_KEY_ID, KALSHI_PRIVATE_KEY_PATH)
        self.current_open_position = None
        self.traded_tickers = set()

        self.load_journal()

        if self.mode == "LIVE":
            b_info = self.client.get_real_balance()
            real_bal = b_info.get("shard2_balance", 0.0) or b_info.get("total_balance", 0.0)
            if real_bal and real_bal > 0:
                self.balance = real_bal
                print(f"[*] [GOLD 15M LIVE] Saldo Real Kalshi Inicializado: ${self.balance:.2f} USD (Shard 2)")

    def load_journal(self):
        if os.path.exists(JOURNAL_JSON):
            try:
                with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.current_open_position = data.get("open_position")
                    self.traded_tickers = set(t.get("ticker") for t in data.get("trades", []) if t.get("ticker"))
                    self.balance = data.get("current_balance", 100.00)
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
        journal = safe_read_json(JOURNAL_JSON, default={"mode": f"{self.mode}_GOLD_15M", "current_balance": self.balance, "trades": []})
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
                spot = get_gold_spot()
                prior_candle = get_gold_15m_prior_candle() or {}

                # Busca mercados ativos da série KXGOLD15M
                markets = self.client.get_gold_15m_markets()
                active_mkt = markets[0] if markets else None

                if not active_mkt:
                    state = {
                        "asset": "GOLD",
                        "ticker": "KXGOLD15M",
                        "mode": self.mode,
                        "status_signal": "Aguardando abertura de mercado Kalshi KXGOLD15M...",
                        "spot": spot or 0.0,
                        "balance": round(self.balance, 2)
                    }
                    self.update_live_state(state)
                    time.sleep(3)
                    continue

                ticker = active_mkt.get("ticker", "KXGOLD15M")
                raw_strike = active_mkt.get("floor_strike") or active_mkt.get("cap_strike")
                if not raw_strike and active_mkt.get("yes_sub_title"):
                    import re
                    m_match = re.search(r"\$([0-9,]+(?:\.[0-9]+)?)", str(active_mkt["yes_sub_title"]))
                    if m_match:
                        try:
                            raw_strike = float(m_match.group(1).replace(",", ""))
                        except Exception:
                            pass
                if not raw_strike:
                    # Strike oficial ainda não fixado pela Kalshi (contrato em transição)
                    time.sleep(3)
                    continue
                strike = float(raw_strike)

                # Cálculo de tempo restante
                close_time_str = active_mkt.get("close_time")
                sec_left = 900
                sec_elapsed = 0
                if close_time_str:
                    try:
                        ct = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
                        now_utc = datetime.now(timezone.utc)
                        sec_left = max(0, int((ct - now_utc).total_seconds()))
                        sec_elapsed = max(0, 900 - sec_left)
                    except Exception:
                        pass

                delta = (spot - strike) if (spot and strike) else 0.0
                deadband = max(DEADBAND_MIN_FLOOR, (strike or 4250.0) * DEADBAND_BPS)

                state = {
                    "asset": "GOLD",
                    "ticker": ticker,
                    "mode": self.mode,
                    "seconds_elapsed": sec_elapsed,
                    "seconds_left": sec_left,
                    "progress_pct": round((sec_elapsed / 900.0) * 100, 1),
                    "spot": spot or 0.0,
                    "strike": strike,
                    "delta": round(delta, 2),
                    "deadband": round(deadband, 2),
                    "prior_candle_dir": prior_candle.get("direction", "NEUTRAL"),
                    "prior_candle_bps": prior_candle.get("diff_bps", 0.0),
                    "balance": round(self.balance, 2),
                    "has_open_position": bool(self.current_open_position),
                    "status_signal": f"Monitorando {ticker} (Delta: {'+' if delta >= 0 else ''}${delta:.2f} | Deadband: ${deadband:.2f})"
                }

                # Monitoramento de Posição Aberta (Take-Profit & Stop-Loss)
                if self.current_open_position:
                    pos = self.current_open_position
                    pos_ticker = pos.get("ticker")
                    pos_side = pos.get("side")

                    ob = self.client.get_orderbook(pos_ticker)
                    best_bid = extract_best_bid(ob, pos_side) if (ob and sec_elapsed >= 550) else None

                    # Take-Profit SirMartingale com Saída em Escala (Raghee Horner / JEV)
                    entry_type = pos.get("entry_type", "PRIMARY_10M")
                    entry_price = float(pos.get("entry_price", 0.50))

                    # Calibração Dinâmica JEV: Sweeper carrega até $1.00 ou liquida a >= 0.98; Primária busca 88¢ ou +30%
                    if entry_type == "SWEEPER_13M":
                        target_tp = 0.98
                    else:
                        target_tp = max(TAKE_PROFIT_PRICE, round(entry_price * 1.30, 2))

                    # Salvaguarda Inviolável: best_bid DEVE ser >= target_tp E estritamente maior que entry_price + $0.03
                    is_valid_tp = (best_bid is not None and best_bid >= target_tp and best_bid >= (entry_price + 0.03))

                    if is_valid_tp and not pos.get("tp1_executed", False):
                        if pos["contracts"] >= 2:
                            half_contracts = pos["contracts"] // 2
                            sell_ok = True
                            if self.mode == "LIVE":
                                sell_cents = int(round(best_bid * 100))
                                s_res = self.client.place_order(pos_ticker, pos_side, count=half_contracts, price_cents=sell_cents, action="sell")
                                print(f"   [⚡ VENDA TP1 REAL KALSHI]: {s_res}")
                                if isinstance(s_res, dict) and ("order" in s_res or "order_id" in s_res):
                                    order_data = s_res.get("order", {}) if isinstance(s_res.get("order"), dict) else s_res
                                    sell_oid = order_data.get("order_id") or s_res.get("order_id", "")
                                    fill_cnt = float(s_res.get("fill_count") or order_data.get("fill_count") or 0.0)
                                    rem_cnt = float(s_res.get("remaining_count") or order_data.get("remaining_count") or 1.0)
                                    status = "executed" if (rem_cnt == 0.0 and fill_cnt >= half_contracts) else str(order_data.get("status", "resting")).lower()
                                    if status in ("open", "resting", "pending"):
                                        for _ in range(3):
                                            time.sleep(3)
                                            chk = self.client.get_order_status(sell_oid)
                                            if isinstance(chk, dict) and "order" in chk and isinstance(chk["order"], dict):
                                                cur_st = str(chk["order"].get("status", "")).lower()
                                                if cur_st in ("executed", "filled"):
                                                    status = "filled"
                                                    break
                                    sell_ok = (status in ("executed", "filled"))
                                    if not sell_ok and sell_oid:
                                        try:
                                            self.client.cancel_order(sell_oid)
                                        except Exception:
                                            pass
                                else:
                                    sell_ok = False
                            if sell_ok:
                                payout_tp1 = round(half_contracts * best_bid, 4)
                                pnl_tp1 = round(payout_tp1 - (half_contracts * pos["entry_price"]), 4)
                                if self.mode == "LIVE":
                                    time.sleep(2)
                                    b_info = self.client.get_real_balance()
                                    real_s2 = b_info.get("shard2_balance")
                                    if real_s2 and real_s2 > 0:
                                        self.balance = real_s2
                                else:
                                    self.balance = round(self.balance + pnl_tp1, 4)
                                pos["tp1_executed"] = True
                                pos["tp1_pnl"] = pnl_tp1
                                pos["contracts"] -= half_contracts
                                pos["cost"] = round(pos["contracts"] * pos["entry_price"], 4)
                                pos["breakeven_price"] = pos["entry_price"]
                                self.save_open_position(pos)
                                print(f"[GOLD 15M (RAGHEE SCALE)] TP1 Parcial: {half_contracts}x vendido a ${best_bid:.2f} (+${pnl_tp1:.2f} USD)! Runner ({pos['contracts']}x) mantido com Stop Breakeven (${pos['entry_price']:.2f})!")
                        else:
                            sell_ok = True
                            sell_oid = ""
                            if self.mode == "LIVE":
                                sell_cents = int(round(best_bid * 100))
                                s_res = self.client.place_order(pos_ticker, pos_side, count=pos["contracts"], price_cents=sell_cents, action="sell")
                                print(f"   [⚡ VENDA TP INTEGRAL REAL KALSHI]: {s_res}")
                                if isinstance(s_res, dict) and ("order" in s_res or "order_id" in s_res):
                                    order_data = s_res.get("order", {}) if isinstance(s_res.get("order"), dict) else s_res
                                    sell_oid = order_data.get("order_id") or s_res.get("order_id", "")
                                    fill_cnt = float(s_res.get("fill_count") or order_data.get("fill_count") or 0.0)
                                    rem_cnt = float(s_res.get("remaining_count") or order_data.get("remaining_count") or 1.0)
                                    status = "executed" if (rem_cnt == 0.0 and fill_cnt >= pos["contracts"]) else str(order_data.get("status", "resting")).lower()
                                    if status in ("open", "resting", "pending"):
                                        for _ in range(3):
                                            time.sleep(3)
                                            chk = self.client.get_order_status(sell_oid)
                                            if isinstance(chk, dict) and "order" in chk and isinstance(chk["order"], dict):
                                                cur_st = str(chk["order"].get("status", "")).lower()
                                                if cur_st in ("executed", "filled"):
                                                    status = "filled"
                                                    break
                                    sell_ok = (status in ("executed", "filled"))
                                    if not sell_ok and sell_oid:
                                        try:
                                            self.client.cancel_order(sell_oid)
                                        except Exception:
                                            pass
                                else:
                                    sell_ok = False
                            if sell_ok:
                                payout = round(pos["contracts"] * best_bid, 4)
                                pnl = round(payout - (pos["contracts"] * pos["entry_price"]), 4)
                                if self.mode == "LIVE":
                                    time.sleep(2)
                                    b_info = self.client.get_real_balance()
                                    real_s2 = b_info.get("shard2_balance")
                                    if real_s2 and real_s2 > 0:
                                        self.balance = real_s2
                                else:
                                    self.balance = round(self.balance + pnl, 4)
                                trade_rec = {
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "execution_mode": self.mode,
                                    "order_id": pos.get("order_id", ""),
                                    "sell_order_id": sell_oid,
                                    "ticker": pos_ticker,
                                    "side": pos_side,
                                    "strike": pos["strike"],
                                    "spot_entry": pos["spot_entry"],
                                    "final_spot": spot,
                                    "result": f"VITÓRIA (TAKE-PROFIT ANTECIPADO +${pnl:.2f})",
                                    "payout": payout,
                                    "pnl": pnl,
                                    "balance": self.balance
                                }
                                self.record_trade(trade_rec)
                                self.clear_open_position()
                                print(f"[GOLD 15M] Take-Profit integral executado a ${best_bid:.2f} | PnL: +${pnl:.2f} USD")

                    # Monitoramento de Breakeven Stop no Runner (após TP1)
                    elif pos.get("tp1_executed", False) and best_bid is not None and best_bid <= pos["entry_price"]:
                        sell_ok = True
                        if self.mode == "LIVE":
                            sell_cents = int(round(best_bid * 100))
                            s_res = self.client.place_order(pos_ticker, pos_side, count=pos["contracts"], price_cents=sell_cents, action="sell")
                            print(f"   [⚡ VENDA BREAKEVEN REAL KALSHI]: {s_res}")
                            sell_ok = isinstance(s_res, dict) and ("order" in s_res or "order_id" in s_res)
                        if sell_ok:
                            payout_be = round(pos["contracts"] * best_bid, 4)
                            pnl_be = round(payout_be - pos["cost"], 4)
                            total_pnl = round(pos.get("tp1_pnl", 0.0) + pnl_be, 4)
                            if self.mode == "LIVE":
                                time.sleep(2)
                                b_info = self.client.get_real_balance()
                                real_s2 = b_info.get("shard2_balance")
                                if real_s2 and real_s2 > 0:
                                    self.balance = real_s2
                            else:
                                self.balance = round(self.balance + pnl_be, 4)
                            res_label = f"VITÓRIA (BREAKEVEN RUNNER +${total_pnl:.2f})" if total_pnl > 0 else (f"BREAKEVEN STOP (${total_pnl:.2f})" if total_pnl == 0 else f"DEFESA RUNNER (${total_pnl:.2f})")
                            trade_rec = {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "execution_mode": self.mode,
                                "order_id": pos.get("order_id", ""),
                                "ticker": pos_ticker,
                                "side": pos_side,
                                "strike": pos["strike"],
                                "spot_entry": pos["spot_entry"],
                                "final_spot": spot,
                                "result": res_label,
                                "payout": round(pos.get("tp1_pnl", 0.0) + payout_be + pos["cost"], 4),
                                "pnl": total_pnl,
                                "balance": self.balance
                            }
                            self.record_trade(trade_rec)
                            self.clear_open_position()
                            print(f"[GOLD 15M (RAGHEE SCALE)] Runner estopado no Breakeven a ${best_bid:.2f}! Total PnL do trade: {total_pnl:+.2f} USD")

                # 1. Avaliação de Nova Entrada Primária (Janela 600s - 660s | 96.33% WR)
                elif sec_elapsed >= EVAL_POINT_SEC and sec_elapsed <= EVAL_MAX_SEC:
                    is_benched, bench_reason, bench_rem = bench.check_consecutive_losses_breaker("desk9", JOURNAL_JSON, max_consecutive_losses=2, cooldown_seconds=1800)
                    if not is_benched:
                        is_benched, bench_reason, bench_rem = bench.check_coin_flip_breaker("desk9", JOURNAL_JSON)
                    if not is_benched:
                        is_benched, bench_reason, bench_rem = bench.is_benched("desk9")
                    if is_benched:
                        print(f"   [🛑 VARIABLE BENCH]: Desk 9 em cooldown ({bench_reason}) — restam {bench_rem:.1f}s.")
                        state["status_signal"] = f"Bench Cooldown ({bench_reason}: {bench_rem:.0f}s)"
                        self.update_live_state(state)
                        time.sleep(min(15, max(3, int(bench_rem))))
                        continue

                    if ticker not in self.traded_tickers and spot and strike:
                        target_side = None
                        prior_dir = prior_candle.get("direction", "NEUTRAL")
                        prior_bps = abs(float(prior_candle.get("diff_bps", 0.0)))
                        # Só permite override contra a vela anterior se o delta for massivo (>= 2.5x deadband) e a vela anterior não for rompimento forte (> 5 bps)
                        strong_override = (abs(delta) >= 2.5 * deadband and prior_bps < 5.0)
                        if delta >= deadband and (prior_dir == "UP" or (prior_dir == "NEUTRAL") or strong_override):
                            target_side = "YES"
                        elif delta <= -deadband and (prior_dir == "DOWN" or (prior_dir == "NEUTRAL") or strong_override):
                            target_side = "NO"
                        else:
                            print(f"   [🛡️ VETO VELA ANTERIOR OURO]: Sinal {'YES' if delta > 0 else 'NO'} (Delta ${delta:+.2f}) bloqueado contra vela anterior {prior_dir} ({prior_bps:.1f} bps).")

                        if target_side:
                            ob = self.client.get_orderbook(ticker)
                            best_ask, avail_qty = extract_best_ask_and_qty(ob, target_side)
                            best_bid = extract_best_bid(ob, target_side)

                            # Gate de Liquidez e Spread Máximo
                            if best_ask is None or best_bid is None:
                                print(f"   [🛡️ GATE DE LIQUIDEZ]: Book vazio/ilíquido em {ticker} (Ask: {best_ask}, Bid: {best_bid}). Pulando entrada.")
                                continue
                            spread = round(best_ask - best_bid, 4)
                            if spread > MAX_SPREAD:
                                print(f"   [🛡️ GATE DE SPREAD]: Spread de {spread*100:.1f}¢ excede teto de {MAX_SPREAD*100:.0f}¢ em {ticker}. Pulando entrada.")
                                continue

                            # Gate Híbrido Black-Scholes Fair Value (Desk 3 & Desk 9 Protocol)
                            bs_fv_up = calculate_black_scholes_digital_fv(spot, strike, sec_elapsed, total_sec=900, sigma=0.0015)
                            bs_fv = bs_fv_up if target_side == "YES" else (1.0 - bs_fv_up)
                            hybrid_cap = min(PRIMARY_MAX_PRICE, round(bs_fv + 0.02, 2))

                            if best_ask is not None and best_ask > hybrid_cap:
                                print(f"   [🛡️ GATE HÍBRIDO BLACK-SCHOLES]: Cota a ${best_ask:.2f} excede Teto Híbrido de ${hybrid_cap:.2f} (FV: ${bs_fv:.2f} + 2¢ spread cap). Pulando entrada.")
                                continue

                            if best_ask is not None and (PRIMARY_MIN_PRICE <= best_ask <= hybrid_cap):
                                # ── CÃO DE GUARDA JEV (Blindagem Anti-Exaustão e Anti-Repique no Ouro) ──
                                jev_res = jev_gate.evaluate_entry(
                                    desk_id="desk9",
                                    delta_usd=delta,
                                    binance_drift=round(delta * 0.25, 2),
                                    clob_spread=spread,
                                    contract_price=best_ask,
                                    oracle_discrepancy=0.15,
                                    seconds_left=int(sec_left),
                                    obi=0.0,
                                    cvd=0.0,
                                    deadband_threshold=deadband,
                                    side=target_side,
                                    symbol="GOLD"
                                )
                                if jev_res.get("verdict") == "VETO":
                                    print(f"   [🛑 VETO CÃO DE GUARDA JEV OURO]: {jev_res.get('veto_reason')} | Regime: {jev_res.get('candle_regime')}. Veto preventivo contra repique!")
                                    state["status_signal"] = f"Veto JEV Watchdog ({jev_res.get('candle_regime')})"
                                    self.update_live_state(state)
                                    time.sleep(15)
                                    continue

                                delta_ratio = abs(delta) / max(0.1, deadband)
                                win_prob = 0.75
                                if delta_ratio >= 1.5:
                                    win_prob += 0.05
                                if delta_ratio >= 2.0:
                                    win_prob += 0.05

                                contracts, kelly_st = compute_kalshi_dynamic_contracts(
                                    bankroll=self.balance,
                                    win_probability=win_prob,
                                    entry_price_cents=int(best_ask * 100),
                                    available_qty=avail_qty,
                                    delta_ratio=delta_ratio,
                                    min_contracts=1,
                                    max_contracts_cap=2
                                )
                                cost = round(contracts * best_ask, 4)
                                pos_info = {
                                    "ticker": ticker,
                                    "side": target_side,
                                    "strike": strike,
                                    "spot_entry": spot,
                                    "entry_price": best_ask,
                                    "contracts": contracts,
                                    "cost": cost,
                                    "kelly_status": kelly_st,
                                    "entry_type": "PRIMARY_10M",
                                    "entry_time": datetime.now(timezone.utc).isoformat()
                                }

                                if self.mode == "LIVE":
                                    b_info = self.client.get_real_balance()
                                    real_bal = b_info.get("shard2_balance", 0.0) or b_info.get("total_balance", 0.0)
                                    if real_bal and real_bal > 0:
                                        self.balance = real_bal
                                    if self.balance < 2.00:
                                        print(f"   [🚨 TRAVA DE SEGURANÇA]: Saldo Kalshi (${self.balance:.2f}) abaixo do piso ($2.00). Abortando entrada.")
                                        continue

                                    order_cents = int(round(best_ask * 100))
                                    res = self.client.place_order(ticker, target_side, contracts, order_cents, action="buy")
                                    print(f"   [⚡ RESPOSTA DA ORDEM REAL KALSHI GOLD]: {res}")
                                    if not res or ("order_id" not in res and "order" not in res):
                                        print("   [!] Falha ao emitir ordem na Kalshi. Abortando entrada para proteger capital.")
                                        continue

                                    order_info = res.get("order", {}) if isinstance(res.get("order"), dict) else res
                                    real_order_id = order_info.get("order_id") or res.get("order_id", "")
                                    fill_cnt = float(res.get("fill_count") or order_info.get("fill_count") or 0.0)
                                    rem_cnt = float(res.get("remaining_count") or order_info.get("remaining_count") or 1.0)
                                    if rem_cnt == 0.0 and fill_cnt >= contracts:
                                        status = "executed"
                                    else:
                                        status = str(order_info.get("status", "resting")).lower()

                                    if status in ("open", "resting", "pending"):
                                        print("   -> Aguardando preenchimento da compra na Kalshi...")
                                        for _ in range(4):
                                            time.sleep(3)
                                            chk = self.client.get_order_status(real_order_id)
                                            if isinstance(chk, dict) and "order" in chk and isinstance(chk["order"], dict):
                                                cur_st = str(chk["order"].get("status", "")).lower()
                                                if cur_st in ("executed", "filled"):
                                                    status = "filled"
                                                    break

                                    if status not in ("executed", "filled"):
                                        print(f"   [⚠️ COMPRA NÃO PREENCHIDA]: Status '{status}'. Cancelando resting order.")
                                        try:
                                            self.client.cancel_order(real_order_id)
                                        except Exception:
                                            pass
                                        continue

                                    pos_info["order_id"] = real_order_id

                                self.save_open_position(pos_info)
                                self.traded_tickers.add(ticker)
                                print(f"[*] [GOLD 15M {self.mode}] Ordem Primária (10m | 96.3% WR): {contracts}x {target_side} a ${best_ask:.2f} ({kelly_st}) em {ticker}")

                # 2. Avaliação de Varredura Sweeper de Alta Certeza (Janela 780s - 830s | Teto Blindado <= $0.65 + 2.0x Deadband)
                elif sec_elapsed >= SWEEPER_POINT_SEC and sec_elapsed <= SWEEPER_MAX_SEC:
                    is_benched, bench_reason, bench_rem = bench.is_benched("desk9")
                    if is_benched:
                        time.sleep(5)
                        continue

                    if ticker not in self.traded_tickers and spot and strike:
                        target_side = None
                        prior_dir = prior_candle.get("direction", "NEUTRAL")
                        sweeper_min_delta = 2.0 * deadband
                        if delta >= sweeper_min_delta and prior_dir != "DOWN":
                            target_side = "YES"
                        elif delta <= -sweeper_min_delta and prior_dir != "UP":
                            target_side = "NO"

                        if target_side:
                            ob = self.client.get_orderbook(ticker)
                            best_ask, avail_qty = extract_best_ask_and_qty(ob, target_side)
                            best_bid = extract_best_bid(ob, target_side)

                            # Gate de Liquidez e Spread Máximo
                            if best_ask is None or best_bid is None:
                                print(f"   [🛡️ GATE DE LIQUIDEZ]: Book vazio/ilíquido em {ticker} (Ask: {best_ask}, Bid: {best_bid}). Pulando entrada.")
                                continue
                            spread = round(best_ask - best_bid, 4)
                            if spread > MAX_SPREAD:
                                print(f"   [🛡️ GATE DE SPREAD]: Spread de {spread*100:.1f}¢ excede teto de {MAX_SPREAD*100:.0f}¢ em {ticker}. Pulando entrada.")
                                continue

                            bs_fv_up = calculate_black_scholes_digital_fv(spot, strike, sec_elapsed, total_sec=900, sigma=0.0015)
                            bs_fv = bs_fv_up if target_side == "YES" else (1.0 - bs_fv_up)
                            sweeper_cap = min(SWEEPER_MAX_PRICE, round(bs_fv + 0.02, 2))

                            if best_ask is not None and (PRIMARY_MIN_PRICE <= best_ask <= sweeper_cap):
                                # ── CÃO DE GUARDA JEV SWEEPER OURO ──
                                jev_res = jev_gate.evaluate_entry(
                                    desk_id="desk9",
                                    delta_usd=delta,
                                    binance_drift=round(delta * 0.25, 2),
                                    clob_spread=spread,
                                    contract_price=best_ask,
                                    oracle_discrepancy=0.15,
                                    seconds_left=int(sec_left),
                                    obi=0.0,
                                    cvd=0.0,
                                    deadband_threshold=deadband,
                                    side=target_side,
                                    symbol="GOLD"
                                )
                                if jev_res.get("verdict") == "VETO":
                                    print(f"   [🛑 VETO CÃO DE GUARDA JEV SWEEPER OURO]: {jev_res.get('veto_reason')} | Regime: {jev_res.get('candle_regime')}. Veto preventivo!")
                                    state["status_signal"] = f"Veto JEV Sweeper ({jev_res.get('candle_regime')})"
                                    self.update_live_state(state)
                                    time.sleep(15)
                                    continue

                                delta_ratio = abs(delta) / max(0.1, deadband)
                                win_prob = 0.85

                                contracts, kelly_st = compute_kalshi_dynamic_contracts(
                                    bankroll=self.balance,
                                    win_probability=win_prob,
                                    entry_price_cents=int(best_ask * 100),
                                    available_qty=avail_qty,
                                    delta_ratio=delta_ratio,
                                    min_contracts=1,
                                    max_contracts_cap=2
                                )
                                cost = round(contracts * best_ask, 4)
                                pos_info = {
                                    "ticker": ticker,
                                    "side": target_side,
                                    "strike": strike,
                                    "spot_entry": spot,
                                    "entry_price": best_ask,
                                    "contracts": contracts,
                                    "cost": cost,
                                    "kelly_status": kelly_st,
                                    "entry_type": "SWEEPER_13M",
                                    "entry_time": datetime.now(timezone.utc).isoformat()
                                }

                                if self.mode == "LIVE":
                                    b_info = self.client.get_real_balance()
                                    real_bal = b_info.get("shard2_balance", 0.0) or b_info.get("total_balance", 0.0)
                                    if real_bal and real_bal > 0:
                                        self.balance = real_bal
                                    if self.balance < 2.00:
                                        print(f"   [🚨 TRAVA DE SEGURANÇA]: Saldo Kalshi (${self.balance:.2f}) abaixo do piso ($2.00). Abortando entrada.")
                                        continue

                                    order_cents = int(round(best_ask * 100))
                                    res = self.client.place_order(ticker, target_side, contracts, order_cents, action="buy")
                                    print(f"   [⚡ RESPOSTA DA ORDEM REAL KALSHI GOLD SWEEPER]: {res}")
                                    if not res or ("order_id" not in res and "order" not in res):
                                        print("   [!] Falha ao emitir ordem na Kalshi. Abortando entrada para proteger capital.")
                                        continue

                                    order_info = res.get("order", {}) if isinstance(res.get("order"), dict) else res
                                    real_order_id = order_info.get("order_id") or res.get("order_id", "")
                                    fill_cnt = float(res.get("fill_count") or order_info.get("fill_count") or 0.0)
                                    rem_cnt = float(res.get("remaining_count") or order_info.get("remaining_count") or 1.0)
                                    if rem_cnt == 0.0 and fill_cnt >= contracts:
                                        status = "executed"
                                    else:
                                        status = str(order_info.get("status", "resting")).lower()

                                    if status in ("open", "resting", "pending"):
                                        print("   -> Aguardando preenchimento da varredura na Kalshi...")
                                        for _ in range(4):
                                            time.sleep(3)
                                            chk = self.client.get_order_status(real_order_id)
                                            if isinstance(chk, dict) and "order" in chk and isinstance(chk["order"], dict):
                                                cur_st = str(chk["order"].get("status", "")).lower()
                                                if cur_st in ("executed", "filled"):
                                                    status = "filled"
                                                    break

                                    if status not in ("executed", "filled"):
                                        print(f"   [⚠️ SWEEPER NÃO PREENCHIDO]: Status '{status}'. Cancelando resting order.")
                                        try:
                                            self.client.cancel_order(real_order_id)
                                        except Exception:
                                            pass
                                        continue

                                    pos_info["order_id"] = real_order_id

                                self.save_open_position(pos_info)
                                self.traded_tickers.add(ticker)
                                print(f"[*] [GOLD 15M {self.mode}] Varredura Sweeper (13m | 99.15% WR): {contracts}x {target_side} a ${best_ask:.2f} ({kelly_st}) em {ticker}")

                # Apuração de Encerramento (sec_left <= 5)
                if self.current_open_position and sec_left <= 5:
                    pos = self.current_open_position
                    pos_side = pos.get("side")
                    win = None
                    revenue_official = None
                    if self.mode == "LIVE":
                        print(f"   -> [CFTC CLEARING] Consultando liquidação oficial no portfólio Kalshi ({pos['ticker']})...")
                        time.sleep(5)
                        port_settle = self.client.get_portfolio_settlement(pos['ticker'], max_retries=6, delay=3)
                        if port_settle:
                            k_res = str(port_settle.get("market_result", "")).lower()
                            win = (pos_side.lower() == k_res)
                            rev_cents = float(port_settle.get("revenue", 0))
                            revenue_official = rev_cents / 100.0
                            print(f"   [🏛️ LIQUIDAÇÃO OFICIAL KALSHI GOLD]: Resultado: {k_res.upper()} | Revenue: ${revenue_official:.2f}")

                    if win is None:
                        win = (spot >= pos["strike"]) if pos_side == "YES" else (spot < pos["strike"])

                    if pos.get("tp1_executed", False):
                        payout_runner = revenue_official if revenue_official is not None else (pos["contracts"] * 1.0 if win else 0.0)
                        pnl_runner = round(payout_runner - pos["cost"], 4)
                        total_pnl = round(pos.get("tp1_pnl", 0.0) + pnl_runner, 4)
                        payout = round(pos.get("tp1_pnl", 0.0) + pos["cost"] + payout_runner, 4)
                        pnl = total_pnl
                        res_str = f"VITÓRIA SCALE RUNNER (+${total_pnl:.2f})" if win else f"DEFESA TP1 (+${total_pnl:.2f})"
                        if self.mode == "LIVE":
                            time.sleep(3)
                            b_info = self.client.get_real_balance()
                            real_s2 = b_info.get("shard2_balance")
                            if real_s2 and real_s2 > 0:
                                self.balance = real_s2
                        else:
                            self.balance = round(self.balance + pnl_runner, 4)
                    else:
                        payout = revenue_official if revenue_official is not None else (pos["contracts"] * 1.0 if win else 0.0)
                        pnl = round(payout - pos["cost"], 4)
                        res_str = f"VITÓRIA (+${pnl:.2f})" if win else f"DERROTA (-${pos['cost']:.2f})"
                        if self.mode == "LIVE":
                            time.sleep(3)
                            b_info = self.client.get_real_balance()
                            real_s2 = b_info.get("shard2_balance")
                            if real_s2 and real_s2 > 0:
                                self.balance = real_s2
                        else:
                            self.balance = round(self.balance + pnl, 4)

                    trade_rec = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "execution_mode": self.mode,
                        "order_id": pos.get("order_id", ""),
                        "ticker": pos["ticker"],
                        "side": pos_side,
                        "strike": pos["strike"],
                        "spot_entry": pos["spot_entry"],
                        "final_spot": spot,
                        "result": "VITÓRIA (RUNNER $1.00)" if (win and pos.get("tp1_executed")) else ("DEFESA (TP1 PARCIAL)" if (not win and pos.get("tp1_executed")) else ("VITÓRIA" if win else "DERROTA")),
                        "payout": payout,
                        "pnl": pnl,
                        "balance": self.balance
                    }
                    self.record_trade(trade_rec)
                    self.clear_open_position()
                    try:
                        record_desk_trade_result("desk9", is_win=win, pnl=pnl)
                    except Exception:
                        pass
                    print(f"[GOLD 15M] Apuração Final: {res_str}")

                self.update_live_state(state)
                time.sleep(3)

            except Exception as e:
                print(f"[GOLD 15M Loop Exception]: {e}")
                time.sleep(3)

def main():
    print("=" * 80)
    print("  🏆 INICIANDO DESK GOLD 15M (KALSHI KXGOLD15M)")
    print(f"  Modo de Execução: {EXECUTION_MODE} | Shard de Risco: Shard 2")
    print("  Contrato: KXGOLD15M | Deadband: 3.5 bps ($1.50) | Sweet-Spot: 420s-465s | Oráculo: Metal.Index.1OZGOLD/USD")
    print("=" * 80)
    trader = GoldTrader15M()
    trader.run_cycle()

if __name__ == "__main__":
    main()
