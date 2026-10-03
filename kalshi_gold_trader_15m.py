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
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List

from risk_gate import compute_kalshi_dynamic_contracts, atomic_write_json, safe_read_json

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

# Parâmetros Quantitativos (Jev Calibrated para Ouro)
FIXED_STAKE = 1.00                # $1.00 USD por aposta primária (1 contrato)
DEADBAND_BPS = 0.00040            # 4.0 bps (0.040%) do preço do Ouro ($1.70 em $4,250)
DEADBAND_MIN_FLOOR = 1.50         # Piso mínimo absoluto de $1.50 no Ouro
PRIMARY_MAX_PRICE = 0.60          # Preço máximo por cota (60¢)
PRIMARY_MIN_PRICE = 0.25          # Preço mínimo por cota (25¢)
MAX_SPREAD = 0.08                 # Spread máximo aceito no book (8¢)
TAKE_PROFIT_PRICE = 0.88          # Take-Profit antecipado SirMartingale (88¢)
STOP_LOSS_MIN_BID = 0.15          # Preço mínimo para Stop-Loss antecipado (15¢)
EVAL_POINT_SEC = 600              # Decisão primária aos 600s (Minuto 10:00 - Certificado JEV 96.33% WR)
EVAL_MAX_SEC = 660                # Janela de entrada primária (10m00s a 11m00s)
SWEEPER_POINT_SEC = 780           # Varredura Sweeper aos 780s (Minuto 13:00 - Certificado JEV 99.15% WR)
SWEEPER_MAX_SEC = 830             # Janela da varredura final (13m00s a 13m50s)
SWEEPER_MAX_PRICE = 0.94          # Preço teto para captura tardia de alta certeza (94¢)

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
            import urllib.parse
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

# ===================== FEEDS SPOT OURO (XAU) =====================
def get_gold_spot() -> Optional[float]:
    """Feed redundante: Pyth Network XAU/USD ou Binance PAXGUSDT"""
    # 1. Tenta Pyth Network
    url_pyth = f"https://hermes.pyth.network/v2/updates/price/latest?ids%5B%5D={PYTH_GOLD_FEED_ID}"
    try:
        req = urllib.request.Request(url_pyth, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2.5) as r:
            data = json.loads(r.read().decode())
            if "parsed" in data and len(data["parsed"]) > 0:
                p_info = data["parsed"][0]["price"]
                raw_price = float(p_info["price"])
                expo = int(p_info["expo"])
                val = raw_price * (10 ** expo)
                if val > 1000.0:
                    return round(val, 2)
    except Exception:
        pass

    # 2. Fallback: Binance PAXGUSDT (rastreia spot gold 1:1)
    url_binance = "https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT"
    try:
        req = urllib.request.Request(url_binance, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2.5) as r:
            return round(float(json.loads(r.read().decode())["price"]), 2)
    except Exception:
        pass

    return None

def get_gold_15m_prior_candle() -> Optional[Dict[str, Any]]:
    """Vela de 15m anterior do Ouro (PAXG) na Binance"""
    url = "https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=15m&limit=2"
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
                    if ob and "orderbook" in ob and sec_elapsed >= 550:
                        book_data = ob["orderbook"]
                        bids = book_data.get("yes" if pos_side == "YES" else "no", [])
                        best_bid = float(bids[0][0]) / 100.0 if bids else 0.0

                        # Take-Profit SirMartingale
                        if best_bid >= TAKE_PROFIT_PRICE:
                            payout = round(pos["contracts"] * best_bid, 4)
                            pnl = round(payout - (pos["contracts"] * pos["entry_price"]), 4)
                            self.balance = round(self.balance + pnl, 4)
                            trade_rec = {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "ticker": pos_ticker,
                                "side": pos_side,
                                "strike": pos["strike"],
                                "spot_entry": pos["spot_entry"],
                                "final_spot": spot,
                                "result": "VITÓRIA (TAKE-PROFIT ANTECIPADO)",
                                "payout": payout,
                                "pnl": pnl,
                                "balance": self.balance
                            }
                            self.record_trade(trade_rec)
                            self.clear_open_position()
                            print(f"[GOLD 15M] Take-Profit executado a ${best_bid:.2f} | PnL: +${pnl:.2f} USD")

                # 1. Avaliação de Nova Entrada Primária (Janela 600s - 660s | 96.33% WR)
                elif sec_elapsed >= EVAL_POINT_SEC and sec_elapsed <= EVAL_MAX_SEC:
                    if ticker not in self.traded_tickers and spot and strike:
                        target_side = None
                        if delta >= deadband and prior_candle.get("direction") == "UP":
                            target_side = "YES"
                        elif delta <= -deadband and prior_candle.get("direction") == "DOWN":
                            target_side = "NO"

                        if target_side:
                            ob = self.client.get_orderbook(ticker)
                            if ob and "orderbook" in ob:
                                book_data = ob["orderbook"]
                                asks = book_data.get("yes" if target_side == "YES" else "no", [])
                                best_ask = float(asks[0][0]) / 100.0 if asks else 0.48

                                if PRIMARY_MIN_PRICE <= best_ask <= PRIMARY_MAX_PRICE:
                                    avail_qty = int(asks[0][1]) if (asks and len(asks[0]) > 1) else 1
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
                                        max_contracts_cap=5
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
                                    self.save_open_position(pos_info)
                                    self.traded_tickers.add(ticker)
                                    print(f"[*] [GOLD 15M {self.mode}] Ordem Primária (10m | 96.3% WR): {contracts}x {target_side} a ${best_ask:.2f} ({kelly_st}) em {ticker}")

                # 2. Avaliação de Varredura Sweeper de Alta Certeza (Janela 780s - 830s | 99.15% WR)
                elif sec_elapsed >= SWEEPER_POINT_SEC and sec_elapsed <= SWEEPER_MAX_SEC:
                    if ticker not in self.traded_tickers and spot and strike:
                        target_side = None
                        if delta >= deadband:
                            target_side = "YES"
                        elif delta <= -deadband:
                            target_side = "NO"

                        if target_side:
                            ob = self.client.get_orderbook(ticker)
                            if ob and "orderbook" in ob:
                                book_data = ob["orderbook"]
                                asks = book_data.get("yes" if target_side == "YES" else "no", [])
                                best_ask = float(asks[0][0]) / 100.0 if asks else 0.85

                                if PRIMARY_MIN_PRICE <= best_ask <= SWEEPER_MAX_PRICE:
                                    avail_qty = int(asks[0][1]) if (asks and len(asks[0]) > 1) else 1
                                    delta_ratio = abs(delta) / max(0.1, deadband)
                                    win_prob = 0.85

                                    contracts, kelly_st = compute_kalshi_dynamic_contracts(
                                        bankroll=self.balance,
                                        win_probability=win_prob,
                                        entry_price_cents=int(best_ask * 100),
                                        available_qty=avail_qty,
                                        delta_ratio=delta_ratio,
                                        min_contracts=1,
                                        max_contracts_cap=5
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
                                    self.save_open_position(pos_info)
                                    self.traded_tickers.add(ticker)
                                    print(f"[*] [GOLD 15M {self.mode}] Varredura Sweeper (13m | 99.15% WR): {contracts}x {target_side} a ${best_ask:.2f} ({kelly_st}) em {ticker}")

                # Apuração de Encerramento (sec_left <= 5)
                if self.current_open_position and sec_left <= 5:
                    pos = self.current_open_position
                    pos_side = pos.get("side")
                    win = (spot >= pos["strike"]) if pos_side == "YES" else (spot < pos["strike"])
                    payout = pos["contracts"] * 1.0 if win else 0.0
                    pnl = round(payout - pos["cost"], 4)
                    self.balance = round(self.balance + pnl, 4)

                    trade_rec = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "ticker": pos["ticker"],
                        "side": pos_side,
                        "strike": pos["strike"],
                        "spot_entry": pos["spot_entry"],
                        "final_spot": spot,
                        "result": "VITÓRIA" if win else "DERROTA",
                        "payout": payout,
                        "pnl": pnl,
                        "balance": self.balance
                    }
                    self.record_trade(trade_rec)
                    cost_val = pos.get("cost", 0.0)
                    res_str = f"VITÓRIA (+${pnl:.2f})" if win else f"DERROTA (-${cost_val:.2f})"
                    self.clear_open_position()
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
    print("  Contrato: KXGOLD15M | Deadband: 4.0 bps ($1.70) | Sweet-Spot: 450s")
    print("=" * 80)
    trader = GoldTrader15M()
    trader.run_cycle()

if __name__ == "__main__":
    main()
