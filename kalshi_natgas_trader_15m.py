"""
Desk 5: Kalshi Natural Gas 15-Minute Algo Trader (KXNATGAS15M)
=============================================================
- Protocolo Oficial: Kalshi Trade API v2 (Autenticação Criptográfica RSA-PSS SHA-256)
- Mercado: KXNATGAS15M (Natural Gas price up in next 15 mins?)
- Oráculo de Liquidação Oficial: Pyth Network (Commodities.Index.NATGAS/USD)
- Feed de Referência Spot: Henry Hub Natural Gas Continuous (NG=F / NYMEX:NG1!)
- Gestão de Risco & Estratégia Quantitativa:
  * Ponto de Avaliação Ótimo: 450s (50% da vela de 15m)
  * Deadband Dinâmico Scale-Invariant: 10.0 bps (piso mínimo de $0.003 / 0.3¢ por MMBtu)
  * Filtro Macro Jev: Confirmação com a última vela fechada de 15m do Gás Natural
  * Teto de Preço: Máximo de $0.60 por cota (evita assimetria negativa de risco)
  * Take-Profit Antecipado (SirMartingale): Venda com lucro travado se cota atingir >= $0.86
  * Fill-or-Cancel Estrito: Polling de até 16s; cancelamento e aborto se ordem ficar 'resting'
  * Liquidação Oficial: Consulta direta ao endpoint oficial da Kalshi (/markets/{ticker})
  * Shard de Execução: Shard 2 (Financials, Crypto & Commodities)
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
import base64
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List

from risk_gate import compute_kalshi_dynamic_contracts

# Caminhos dos arquivos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
JOURNAL_JSON = os.path.join(BASE_DIR, "kalshi_natgas_15m_journal.json")
LIVE_STATE_JSON = os.path.join(BASE_DIR, "kalshi_natgas_15m_live_state.json")

# Configurações de API Kalshi
KALSHI_API_PROD = "https://external-api.kalshi.com/trade-api/v2"
KALSHI_API_DEMO = "https://demo-api.kalshi.co/trade-api/v2"

# Parâmetros Quantitativos (Jev Calibrated para Natural Gas)
FIXED_STAKE = 1.00                # $1.00 USD por aposta primária (1 contrato)
DEADBAND_BPS = 0.0010            # 10.0 bps (0.10%) do preço do Gás Natural
DEADBAND_MIN_FLOOR = 0.0040       # Piso mínimo calibrado via Databento NYMEX ($0.0040 / 0.4¢ por MMBtu)
PRIMARY_MAX_PRICE = 0.60          # Preço máximo por cota (60¢)
PRIMARY_MIN_PRICE = 0.25          # Preço mínimo por cota (25¢)
MAX_SPREAD = 0.08                 # Spread máximo aceito no book (8¢)
TAKE_PROFIT_PRICE = 0.86          # Take-Profit antecipado estilo SirMartingale (86¢)
STOP_LOSS_MIN_BID = 0.15          # Preço mínimo para Stop-Loss antecipado (15¢)
EVAL_POINT_SEC = 450              # Ponto de decisão aos 450s (metade da vela de 15m)
REQUIRE_PRIOR_CANDLE = True       # Filtro Jev Trend Continuation
EXCHANGE_INDEX = 2                # Shard 2 (Commodities)
DRAWDOWN_FLOOR = 2.00             # Piso de proteção da Shard 2 ($2.00 USD)

# ==============================================================================
# ESCUDO DE CHOQUE EIA (EIA Shock Shield - Quintas-feiras às 10:30 AM ET / 14:30 UTC)
# Calibrado em 53 semanas de dados CME Globex TBBO (Databento):
# Deslocamento mediano na EIA salta 800% de 15.3 bps para 119.8 bps ($0.0340/MMBtu).
# Volume salta para 3.500-7.500 contratos por vela de 15m.
# ==============================================================================
EIA_DEADBAND_BPS = 0.0025         # 25.0 bps (0.25%) durante a janela de choque da EIA
EIA_DEADBAND_MIN_FLOOR = 0.0080   # Piso mínimo de $0.0080 (0.8¢/MMBtu) para filtrar micro-ruído inicial
EIA_EVAL_POINT_SEC = 180          # Ponto de decisão antecipado aos 180s (3m) na EIA se rompimento confirmado

def is_eia_release_window(dt_utc: datetime) -> bool:
    """
    Verifica se o momento atual coincide com a janela de divulgação do relatório semanal da EIA:
    Toda quinta-feira das 10:28 às 10:45 AM ET (Eastern Time).
    """
    try:
        dt_et = dt_utc.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        dt_et = dt_utc - timedelta(hours=4)
    # weekday: 3 = Quinta-feira
    # Janela: 10:28 ET até 10:45 ET (cobre a vela das 10:30 ET)
    return dt_et.weekday() == 3 and dt_et.hour == 10 and (28 <= dt_et.minute <= 45)

def load_env_config() -> Dict[str, str]:
    """Carrega variáveis do arquivo .env"""
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
EXECUTION_MODE = ENV_CFG.get("NATGAS_15M_MODE", "PAPER").upper()
KALSHI_KEY_ID = ENV_CFG.get("KALSHI_KEY_ID", "")
raw_key_path = ENV_CFG.get("KALSHI_PRIVATE_KEY_PATH", "kalshi.txt")
KALSHI_PRIVATE_KEY_PATH = raw_key_path if os.path.isabs(raw_key_path) else os.path.join(BASE_DIR, raw_key_path)

# ===================== CLIENTE KALSHI API V2 (RSA-PSS) =====================
class KalshiClient:
    def __init__(self, key_id: str, private_key_pem_path: str, is_demo: bool = False):
        self.key_id = key_id
        self.base_url = KALSHI_API_DEMO if is_demo else KALSHI_API_PROD
        self.private_key = None
        
        if os.path.exists(private_key_pem_path):
            try:
                from cryptography.hazmat.primitives import serialization
                with open(private_key_pem_path, "rb") as f:
                    self.private_key = serialization.load_pem_private_key(f.read(), password=None)
            except Exception as e:
                print(f"[Aviso Kalshi NatGas] Chave privada PEM não pôde ser carregada: {e}")

    def _sign(self, method: str, path: str, timestamp_ms: int) -> str:
        if not self.private_key:
            return ""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        
        clean_path = path.split('?')[0]
        msg = f"{timestamp_ms}{method}{clean_path}".encode('utf-8')
        sig = self.private_key.sign(
            msg,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
        return base64.b64encode(sig).decode('utf-8')

    def request(self, method: str, endpoint: str, params: dict = None, body: dict = None, auth_required: bool = False) -> Optional[dict]:
        path = f"/trade-api/v2{endpoint}"
        url = f"{self.base_url}{endpoint}"
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url += f"?{query}"

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "KalshiNatGas15mAlgoTrader/2.0"
        }

        if auth_required:
            ts = int(time.time() * 1000)
            sig = self._sign(method.upper(), path, ts)
            headers["KALSHI-ACCESS-KEY"] = self.key_id
            headers["KALSHI-ACCESS-TIMESTAMP"] = str(ts)
            headers["KALSHI-ACCESS-SIGNATURE"] = sig

        data_bytes = json.dumps(body).encode('utf-8') if body else None
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method.upper())

        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8', errors='ignore')
            print(f"[Kalshi NatGas API Erro {e.code}]: {err_body}")
            return None
        except Exception as e:
            print(f"[Kalshi NatGas Request Erro]: {e}")
            return None

    def get_real_balance(self) -> Dict[str, float]:
        """Consulta o saldo real na Kalshi via API v2"""
        res = self.request("GET", "/portfolio/balance", auth_required=True)
        shard2_bal = 0.0
        total_bal = 0.0
        if res:
            for b in res.get("balance_breakdown", []):
                if b.get("exchange_index") == EXCHANGE_INDEX:
                    shard2_bal = float(b.get("balance", 0.0))
            total_bal = float(res.get("balance_dollars", shard2_bal))
        return {
            "shard2_balance": round(shard2_bal, 4),
            "total_balance": round(total_bal, 4)
        }

    def get_natgas_15m_markets(self) -> List[dict]:
        """
        Busca o mercado KXNATGAS15M atualmente em andamento na Kalshi.
        Arquitetura Certificada pelo JEV SystemOne:
        1. Detecção da Janela Diária de Manutenção Kalshi (03:00 - 05:00 ET / 07:00 - 09:00 UTC).
        2. Consulta por Janela Temporal Estrita (min_close_ts / max_close_ts).
        3. Resolução Determinística de Ticker via Fuso ET (KXNATGAS15M-{YY}{MMM}{DD}{HHMM}-{MM}).
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
                print(f"   [🏛️ KALSHI EXCHANGE HALT]: Janela diária oficial de manutenção e clearing ({now_et.strftime('%H:%M')} ET / {now_utc.strftime('%H:%M')} UTC). Nenhum contrato KXNATGAS15M emitido.")
                return []
        except Exception:
            pass

        # 1. Consulta Cirúrgica por Janela Temporal Estrita (min_close_ts / max_close_ts)
        try:
            params = {
                "series_ticker": "KXNATGAS15M",
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
            print(f"   [Desk 5 NatGas Discovery L1]: Erro na consulta temporal: {e}")

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
            det_ticker = f"KXNATGAS15M-{yy}{mmm}{dd}{hhmm}-{mm}"

            res_single = self.request("GET", f"/markets/{det_ticker}")
            if res_single and "market" in res_single:
                m = res_single["market"]
                ct = m.get("close_time")
                if not ct or ct > now_iso:
                    return [m]
        except Exception as e:
            print(f"   [Desk 5 NatGas Discovery L2]: Erro na resolução determinística: {e}")

        # 3. Fallback Resiliente com Ordenação Ascendente por close_time
        try:
            res_fb = self.request("GET", "/markets", params={"series_ticker": "KXNATGAS15M", "min_close_ts": now_ts, "limit": 100})
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
            print(f"   [Desk 5 NatGas Discovery L3]: Erro no fallback: {e}")

        return []

    def get_orderbook(self, ticker: str) -> Optional[dict]:
        """Obtém livro de ordens (order book L2)"""
        return self.request("GET", f"/markets/{ticker}/orderbook")

    def place_order(self, ticker: str, side: str, count: int, price_dollars: str, action: str = "buy") -> Optional[dict]:
        """Envia ordem limit oficial V2 na Kalshi (side='yes' ou 'no', action='buy' ou 'sell')"""
        # Na API V2 single-book da Kalshi (referência oficial auditada na Desk 3):
        # BUY YES  -> side='bid', price = yes_dollars
        # BUY NO   -> side='ask', price = (1.00 - no_dollars)
        # SELL YES -> side='ask', price = yes_dollars
        # SELL NO  -> side='bid', price = (1.00 - no_dollars)
        action = action.lower()
        side = side.lower()
        p_val = float(price_dollars)
        if action == "buy":
            book_side = "bid" if side == "yes" else "ask"
            target_price = p_val if side == "yes" else (1.0 - p_val)
        else:
            book_side = "ask" if side == "yes" else "bid"
            target_price = p_val if side == "yes" else (1.0 - p_val)

        target_price = max(0.01, min(0.99, target_price))

        payload = {
            "ticker": ticker,
            "side": book_side,
            "type": "limit",
            "count": str(count),
            "price": f"{target_price:.4f}",
            "self_trade_prevention_type": "taker_at_cross",
            "time_in_force": "good_till_canceled",
            "client_order_id": f"kng15_{action}_{int(time.time()*1000)}"
        }
        return self.request("POST", "/portfolio/events/orders", body=payload, auth_required=True)

    def cancel_order(self, order_id: str) -> Optional[dict]:
        """Cancela ordem oficial V2 na Kalshi"""
        return self.request("DELETE", f"/portfolio/events/orders/{order_id}?exchange_index={EXCHANGE_INDEX}", auth_required=True)

    def get_order_status(self, order_id: str) -> Optional[dict]:
        """Consulta o status de uma ordem oficial na Kalshi"""
        return self.request("GET", f"/portfolio/events/orders/{order_id}", auth_required=True)

    def get_market_settlement(self, ticker: str, max_retries: int = 5) -> Optional[dict]:
        """Consulta o resultado oficial de liquidação na Kalshi API (status, result)"""
        for _ in range(max_retries):
            res = self.request("GET", f"/markets/{ticker}")
            if res and "market" in res:
                m = res["market"]
                status = str(m.get("status", "")).lower()
                if status in ("settled", "finalized", "closed"):
                    return {
                        "status": status,
                        "result": str(m.get("result", "")).lower(), # 'yes' ou 'no'
                        "settlement_timer": m.get("settlement_timer"),
                        "settlement_value": m.get("settlement_value")
                    }
            time.sleep(3)
        return None

# ===================== FEEDS DE PREÇO SPOT (Henry Hub Natural Gas) =====================
def get_natgas_spot() -> Optional[float]:
    """Preço Spot contínuo do Henry Hub Natural Gas (NG=F) via Yahoo Finance / TradingView"""
    urls = [
        "https://query1.finance.yahoo.com/v8/finance/chart/NG=F?interval=1m&range=1d",
        "https://query2.finance.yahoo.com/v8/finance/chart/NG=F?interval=1m&range=1d"
    ]
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=3) as r:
                d = json.loads(r.read().decode("utf-8"))
                meta = d["chart"]["result"][0]["meta"]
                p = meta.get("regularMarketPrice")
                if p and float(p) > 0:
                    return float(p)
        except Exception:
            pass
    return None

def get_natgas_15m_prior_candle() -> Optional[Dict[str, Any]]:
    """
    Consulta a última vela de 15m FECHADA de Natural Gas para validação de tendência macro.
    Filtro Jev: Trend continuation probability boost.
    Retorna {'dir': 'UP'|'DOWN', 'open': float, 'close': float, 'ret_bps': float}
    """
    urls = [
        "https://query1.finance.yahoo.com/v8/finance/chart/NG=F?interval=15m&range=1d",
        "https://query2.finance.yahoo.com/v8/finance/chart/NG=F?interval=15m&range=1d"
    ]
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=3) as r:
                d = json.loads(r.read().decode("utf-8"))
                quotes = d["chart"]["result"][0]["indicators"]["quote"][0]
                opens = quotes.get("open", [])
                closes = quotes.get("close", [])
                valid = [(o, c) for o, c in zip(opens, closes) if o is not None and c is not None]
                if len(valid) >= 2:
                    prior_o, prior_c = valid[-2]
                    direction = "UP" if prior_c >= prior_o else "DOWN"
                    ret_bps = (abs(prior_c - prior_o) / prior_o) * 10000
                    return {
                        "dir": direction,
                        "open": round(prior_o, 4),
                        "close": round(prior_c, 4),
                        "ret_bps": round(ret_bps, 2)
                    }
        except Exception:
            pass
    return None

# ===================== MOTOR DO DESK 5: KALSHI NATGAS 15M =====================
class KalshiNatGasTrader15M:
    def __init__(self):
        self.client = KalshiClient(KALSHI_KEY_ID, KALSHI_PRIVATE_KEY_PATH)
        self.kalshi_client = self.client
        self.mode = EXECUTION_MODE
        self.balance = 100.00 if self.mode != "LIVE" else 9.05
        self.current_open_position = None
        self.traded_tickers = set()
        if self.mode == "LIVE":
            b_info = self.client.get_real_balance()
            self.balance = b_info.get("shard2_balance") or b_info.get("total_balance") or 9.05
        self.load_journal()

    def load_journal(self):
        if os.path.exists(JOURNAL_JSON):
            try:
                with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.current_open_position = data.get("open_position")
                    self.traded_tickers = set(t.get("ticker") for t in data.get("trades", []) if t.get("ticker"))
                    if self.mode != "LIVE":
                        self.balance = data.get("current_balance", 100.00)
                    else:
                        b_info = self.client.get_real_balance()
                        real_s2 = b_info.get("shard2_balance")
                        if real_s2 and real_s2 > 0:
                            self.balance = real_s2
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
        """Grava estado do radar em JSON para o dashboard ler em tempo real"""
        try:
            with open(LIVE_STATE_JSON, "w", encoding="utf-8") as f:
                json.dump(state_dict, f, indent=2)
        except Exception:
            pass

    def run_cycle(self):
        now_utc = datetime.now(timezone.utc)
        minute = now_utc.minute
        second = now_utc.second

        # Janela de 15 minutos alinhada (00, 15, 30, 45)
        window_minute = (minute // 15) * 15
        elapsed_sec = (minute % 15) * 60 + second
        remaining_sec = 900 - elapsed_sec

        # Verificação de Kill-Switch Global via Arquivo ('HALT' ou 'EMERGENCY_STOP')
        halt_file = os.path.join(BASE_DIR, "HALT")
        emergency_file = os.path.join(BASE_DIR, "EMERGENCY_STOP")
        if os.path.exists(halt_file) or os.path.exists(emergency_file):
            print(f"\n    [🚨 KILL-SWITCH GLOBAL ATIVADO]: Arquivo de emergência detectado. Nenhuma ordem será aberta no NatGas 15m.")
            time.sleep(15)
            return

        print("\n" + "=" * 80)
        print(f" [DESK 5: KALSHI NATGAS 15M] Janela Ativa: {now_utc.strftime('%Y-%m-%d')} {now_utc.hour:02d}:{window_minute:02d}:00 UTC")
        print(f" Tempo Decorrido: {elapsed_sec}s / 900s | Restam: {remaining_sec}s | Modo: {self.mode}")
        print(f" Saldo Real Shard 2: ${self.balance:,.2f} USD")
        print("=" * 80)

        # Verificação do Escudo de Choque da EIA (Quintas 10:28 às 10:45 AM ET)
        eia_active = is_eia_release_window(now_utc)
        target_eval_sec = EIA_EVAL_POINT_SEC if eia_active else EVAL_POINT_SEC

        # 1. Ponto de Avaliação Ótimo: Aos 450s (rotina) ou 180s (choque da EIA)
        if elapsed_sec < target_eval_sec:
            wait = target_eval_sec - elapsed_sec
            prefix = "⚡ [ESCUDO EIA ATIVO]" if eia_active else "[*]"
            print(f"{prefix} Aguardando {wait}s até o ponto quantitativo de decisão ({target_eval_sec}s)...")
            # Atualiza estado no radar
            status_desc = f"Aguardando Ponto de Decisão ({elapsed_sec}s / {target_eval_sec}s)"
            if eia_active:
                status_desc += " [⚡ EIA SHOCK SHIELD]"
            self.update_live_state({
                "ticker": "KXNATGAS15M",
                "seconds_elapsed": elapsed_sec,
                "seconds_left": remaining_sec,
                "progress_pct": round((elapsed_sec / 900) * 100, 1),
                "mode": self.mode,
                "balance": self.balance,
                "status_signal": status_desc
            })
            time.sleep(min(wait, 25))
            return

        # 2. Captura Strike e Spot Atual
        spot_now = get_natgas_spot()
        if not spot_now:
            print("[!] Falha ao ler preço spot Henry Hub. Aguardando...")
            time.sleep(10)
            return

        # Busca mercados Kalshi para a série KXNATGAS15M
        markets = self.client.get_natgas_15m_markets()
        if not markets:
            print("[i] Nenhum mercado KXNATGAS15M aberto no momento no endpoint da Kalshi. Pulando ciclo.")
            time.sleep(30)
            return

        target_market = markets[0]
        ticker = target_market.get("ticker", "KXNATGAS15M-ACTIVE")
        raw_strike = target_market.get("floor_strike") or target_market.get("strike_price")
        if not raw_strike and target_market.get("yes_sub_title"):
            import re
            m_match = re.search(r"\$([0-9,]+(?:\.[0-9]+)?)", str(target_market["yes_sub_title"]))
            if m_match:
                try:
                    raw_strike = float(m_match.group(1).replace(",", ""))
                except Exception:
                    pass
        if not raw_strike:
            print(f"   [Desk 5 NatGas] Strike oficial ainda não fixado pela Kalshi para {ticker}. Aguardando início da vela...")
            time.sleep(30)
            return
        strike_price = float(raw_strike)

        if ticker in self.traded_tickers:
            print(f"   [🛡️ RESTART GUARD]: Ticker {ticker} já foi operado neste ciclo/histórico. Preservando capital e evitando reentrada.")
            self.update_live_state({
                "ticker": ticker,
                "strike": strike_price,
                "spot": spot_now,
                "seconds_elapsed": elapsed_sec,
                "seconds_left": remaining_sec,
                "progress_pct": round((elapsed_sec / 900) * 100, 1),
                "mode": self.mode,
                "balance": self.balance,
                "status_signal": f"RESTART GUARD: Ticker {ticker} já operado nesta janela"
            })
            time.sleep(max(1, remaining_sec))
            return

        delta = spot_now - strike_price
        curr_deadband_bps = EIA_DEADBAND_BPS if eia_active else DEADBAND_BPS
        curr_deadband_floor = EIA_DEADBAND_MIN_FLOOR if eia_active else DEADBAND_MIN_FLOOR
        dynamic_deadband = max(curr_deadband_floor, round(strike_price * curr_deadband_bps, 4))

        print(f"\n[📊 ANÁLISE DE MERCADO KALSHI NATGAS]:")
        if eia_active:
            print(f"   ⚡ [ESCUDO DE CHOQUE EIA ATIVADO]: Quinta-feira 10:30 AM ET detectada!")
            print(f"      Calibração Databento (53 Semanas): Deadband ampliado para {curr_deadband_bps*10000:.1f} bps (${dynamic_deadband:.4f})")
            print(f"      Filtro contra whipsaw ativo: requer confirmação institucional de rompimento real.")
        print(f"   Ticker: {ticker}")
        print(f"   Strike (K): ${strike_price:.5f} | Spot Atual: ${spot_now:.5f} / MMBtu")
        print(f"   Drift Real (Delta): {delta:+.5f} | Deadband Dinâmico: ${dynamic_deadband:.4f} ({curr_deadband_bps*10000:.1f} bps)")

        # 3. Decisão de Entrada
        candidate_side = None
        target_dir = None

        if delta >= dynamic_deadband:
            candidate_side = "yes"
            target_dir = "UP"
            print(f"   -> [SINAL INTRA-VELA]: UP / YES (Drift de +${delta:.4f} superou deadband de ${dynamic_deadband:.4f})")
        elif delta <= -dynamic_deadband:
            candidate_side = "no"
            target_dir = "DOWN"
            print(f"   -> [SINAL INTRA-VELA]: DOWN / NO (Drift de -${abs(delta):.4f} superou deadband de ${dynamic_deadband:.4f})")
        else:
            print(f"   -> [FILTRO DEADBAND]: Delta de ${delta:+.4f} está na zona morta (< ${dynamic_deadband:.4f} | {curr_deadband_bps*10000:.1f} bps). Preservando capital.")
            self.update_live_state({
                "ticker": ticker,
                "strike": strike_price,
                "spot": spot_now,
                "delta": round(delta, 5),
                "deadband": dynamic_deadband,
                "seconds_elapsed": elapsed_sec,
                "seconds_left": remaining_sec,
                "progress_pct": round((elapsed_sec / 900) * 100, 1),
                "mode": self.mode,
                "balance": self.balance,
                "status_signal": f"FILTRO DEADBAND: Drift ${delta:+.4f} na zona morta (< ${dynamic_deadband:.4f})"
            })
            time.sleep(max(1, remaining_sec))
            return

        # 4. Filtro Jev de Continuidade de Tendência
        prior_candle = get_natgas_15m_prior_candle()
        p_dir = "NEUTRAL"
        p_bps = 0.0
        if REQUIRE_PRIOR_CANDLE and prior_candle:
            p_dir = prior_candle["dir"]
            p_bps = prior_candle["ret_bps"]
            print(f"   [🕯️ FILTRO DE VELA ANTERIOR - JEV]: Vela 15m Anterior fechou {p_dir} ({p_bps:.1f} bps)")
            if eia_active:
                print(f"   -> [⚡ ESCUDO EIA ATIVO]: Veto de vela anterior suspenso para choque exógeno de estoques!")
                print(f"      Deslocamento mediano da EIA comprovado via Databento: 119.8 bps. Direção guiada pelo Delta real ({target_dir}).")
            elif p_dir != target_dir:
                print(f"   -> [🛑 VETO JEV]: Sinal intra-vela ({target_dir}) diverge da vela macro anterior ({p_dir}).")
                print("      Estatística Jev: Divergência eleva taxa de whipsaw/reversão. Preservando banca.")
                self.update_live_state({
                    "ticker": ticker,
                    "strike": strike_price,
                    "spot": spot_now,
                    "delta": round(delta, 5),
                    "deadband": dynamic_deadband,
                    "prior_candle_dir": p_dir,
                    "prior_candle_bps": round(p_bps, 1),
                    "seconds_elapsed": elapsed_sec,
                    "seconds_left": remaining_sec,
                    "progress_pct": round((elapsed_sec / 900) * 100, 1),
                    "mode": self.mode,
                    "balance": self.balance,
                    "status_signal": f"🛡️ VETO JEV: Sinal {target_dir} bloqueado contra contratendência ({p_dir} {p_bps:.1f} bps)"
                })
                time.sleep(max(1, remaining_sec))
                return
            else:
                print(f"   -> [🔥 CONFIRMAÇÃO JEV]: Tendência da vela anterior ({p_dir}) alinhada com drift intra-vela ({target_dir})! Convicção alta.")

        # 5. Consulta Livro de Ofertas (Order Book L2)
        ob = self.client.get_orderbook(ticker)
        best_price = None
        price_dollars = None

        avail_qty = 1
        if ob and "orderbook_fp" in ob:
            ob_fp = ob["orderbook_fp"]
            book_key = "yes_dollars" if candidate_side == "yes" else "no_dollars"
            orders = ob_fp.get(book_key, [])
            if orders:
                best_price = float(orders[-1][0])
                price_dollars = f"{best_price:.4f}"
                if len(orders[-1]) > 1:
                    avail_qty = int(orders[-1][1])

        if not best_price or target_market.get("status") != "active":
            print(f"   [🛡️ FILTRO STATUS/LIQUIDEZ]: Mercado {ticker} não ativo ({target_market.get('status')}) ou livro sem ofertas. Pulando com segurança.")
            self.update_live_state({
                "ticker": ticker,
                "strike": strike_price,
                "spot": spot_now,
                "delta": round(delta, 5),
                "deadband": dynamic_deadband,
                "seconds_elapsed": elapsed_sec,
                "seconds_left": remaining_sec,
                "progress_pct": round((elapsed_sec / 900) * 100, 1),
                "mode": self.mode,
                "balance": self.balance,
                "status_signal": f"Aguardando Mercado Ativo / Liquidez ({ticker})"
            })
            time.sleep(max(1, remaining_sec))
            return

        print(f"   Melhor Preço no Livro para {candidate_side.upper()}: ${best_price:.2f} ({int(best_price*100)}¢)")

        # 6. Filtro de Teto de Preço (EV Protection)
        if best_price > PRIMARY_MAX_PRICE:
            print(f"   [🛡️ FILTRO TETO DE PREÇO]: Cota a {int(best_price*100)}¢ > {int(PRIMARY_MAX_PRICE*100)}¢ (Breakeven desfavorável). Pulando entrada.")
            self.update_live_state({
                "ticker": ticker,
                "strike": strike_price,
                "spot": spot_now,
                "delta": round(delta, 5),
                "deadband": dynamic_deadband,
                "prior_candle_dir": p_dir,
                "prior_candle_bps": round(p_bps, 1),
                "seconds_elapsed": elapsed_sec,
                "seconds_left": remaining_sec,
                "progress_pct": round((elapsed_sec / 900) * 100, 1),
                "mode": self.mode,
                "balance": self.balance,
                "status_signal": f"🛡️ TETO DE PREÇO: Cota {candidate_side.upper()} a {int(best_price*100)}¢ > {int(PRIMARY_MAX_PRICE*100)}¢ (EV Desfavorável)"
            })
            time.sleep(max(1, remaining_sec))
            return

        if best_price < PRIMARY_MIN_PRICE:
            print(f"   [🛡️ FILTRO PISO DE PREÇO]: Cota a {int(best_price*100)}¢ < {int(PRIMARY_MIN_PRICE*100)}¢ (Penny trap). Pulando entrada.")
            self.update_live_state({
                "ticker": ticker,
                "strike": strike_price,
                "spot": spot_now,
                "delta": round(delta, 5),
                "deadband": dynamic_deadband,
                "prior_candle_dir": p_dir,
                "prior_candle_bps": round(p_bps, 1),
                "seconds_elapsed": elapsed_sec,
                "seconds_left": remaining_sec,
                "progress_pct": round((elapsed_sec / 900) * 100, 1),
                "mode": self.mode,
                "balance": self.balance,
                "status_signal": f"🛡️ PISO DE PREÇO: Cota {candidate_side.upper()} a {int(best_price*100)}¢ < {int(PRIMARY_MIN_PRICE*100)}¢ (Penny Trap)"
            })
            time.sleep(max(1, remaining_sec))
            return

        # 7. Execução da Ordem (LIVE ou PAPER) com Kelly Fracionário (25%) e Guardrails
        order_success = False
        buy_filled = False
        order_id = None

        delta_ratio = abs(delta) / max(0.0001, dynamic_deadband)
        win_prob = 0.72
        if delta_ratio >= 1.5:
            win_prob += 0.05
        if delta_ratio >= 2.0:
            win_prob += 0.05

        contracts_bought, kelly_st = compute_kalshi_dynamic_contracts(
            bankroll=self.balance,
            win_probability=win_prob,
            entry_price_cents=int(best_price * 100),
            available_qty=avail_qty,
            delta_ratio=delta_ratio,
            min_contracts=1,
            max_contracts_cap=5
        )

        if self.mode == "LIVE":
            if self.balance < DRAWDOWN_FLOOR:
                print(f"   [🚨 TRAVA DE SEGURANÇA]: Saldo Shard 2 (${self.balance:.2f}) abaixo do piso (${DRAWDOWN_FLOOR:.2f}). Abortando.")
                time.sleep(max(1, remaining_sec))
                return

            print(f"\n   ⚡ [BOLETAGEM REAL KALSHI NATGAS]: Enviando BUY {contracts_bought}x {candidate_side.upper()} @ ${price_dollars} ({kelly_st})...")
            order_res = self.client.place_order(ticker, candidate_side, contracts_bought, price_dollars, action="buy")
            if order_res and "order" in order_res:
                order_id = order_res["order"]["order_id"]
                initial_status = order_res["order"].get("status", "")
                print(f"   -> Ordem enviada! ID: {order_id} | Status Inicial: {initial_status}")

                # Polling de verificação de fill (até 16s)
                poll_deadline = time.time() + 16.0
                while time.time() < poll_deadline:
                    time.sleep(2.5)
                    st_res = self.client.get_order_status(order_id)
                    if st_res and "order" in st_res:
                        current_status = st_res["order"].get("status", "")
                        if current_status in ("executed", "filled"):
                            buy_filled = True
                            order_success = True
                            print(f"   -> [FILL CONFIRMADO]: Ordem {order_id} completamente executada!")
                            break
                        elif current_status in ("canceled", "rejected"):
                            print(f"   -> [ORDEM CANCELADA/REJEITADA]: Status {current_status}.")
                            break

                # Se a ordem continuar como resting no livro sem tomador, cancela
                if not buy_filled:
                    print(f"   [⚠️ FILL-OR-CANCEL]: Ordem não foi preenchida a tempo. Cancelando ordem no livro...")
                    self.client.cancel_order(order_id)
                    print(f"   -> Ordem {order_id} cancelada. Abortando trade para proteger capital.")
                    time.sleep(max(1, remaining_sec))
                    return
            else:
                print(f"   [!] Falha na resposta da API Kalshi ao tentar comprar. Abortando entrada.")
                time.sleep(max(1, remaining_sec))
                return
        else:
            # Modo PAPER
            order_id = f"paper_ng15_{int(time.time()*1000)}"
            order_success = True
            buy_filled = True
            print(f"\n   🧪 [SIMULAÇÃO PAPER REALISTA]: BUY {contracts_bought}x {candidate_side.upper()} @ ${price_dollars} (Ordem: {order_id})")

        # Registra posição em aberto
        pos_info = {
            "ticker": ticker,
            "side": candidate_side,
            "target_dir": target_dir,
            "entry_price": best_price,
            "contracts": contracts_bought,
            "order_id": order_id,
            "entry_time": time.time(),
            "strike": strike_price,
            "spot_entry": spot_now,
            "eia_shield_active": eia_active
        }
        self.save_open_position(pos_info)
        self.traded_tickers.add(ticker)

        # 8. Monitoramento Intra-Vela e Take-Profit (SirMartingale)
        sold_early = False
        early_sell_price = 0.0

        print(f"\n   👀 [MONITORAMENTO ATIVO]: Acompanhando Take-Profit (>= ${TAKE_PROFIT_PRICE:.2f})...")
        while time.time() < (now_utc.timestamp() - (elapsed_sec) + 880):
            time.sleep(5)
            ob_mon = self.client.get_orderbook(ticker)
            if ob_mon and "orderbook_fp" in ob_mon:
                fp = ob_mon["orderbook_fp"]
                b_key = "yes_dollars" if candidate_side == "yes" else "no_dollars"
                b_orders = fp.get(b_key, [])
                if b_orders:
                    current_bid = float(b_orders[-1][0])
                    # Verifica Take-Profit SirMartingale
                    if current_bid >= TAKE_PROFIT_PRICE:
                        print(f"\n   💰 [TAKE PROFIT SIRMARTINGALE]: Bid atingiu ${current_bid:.2f} >= ${TAKE_PROFIT_PRICE:.2f}!")
                        if self.mode == "LIVE":
                            sell_res = self.client.place_order(ticker, candidate_side, contracts_bought, f"{current_bid:.4f}", action="sell")
                            if sell_res and "order" in sell_res:
                                sell_id = sell_res["order"]["order_id"]
                                time.sleep(2)
                                st_sell = self.client.get_order_status(sell_id)
                                if st_sell and st_sell.get("order", {}).get("status") in ("executed", "filled"):
                                    sold_early = True
                                    early_sell_price = current_bid
                                    print(f"      -> Venda antecipada preenchida com sucesso a ${early_sell_price:.2f}!")
                                    break
                                else:
                                    self.client.cancel_order(sell_id)
                        else:
                            sold_early = True
                            early_sell_price = current_bid
                            print(f"      -> [PAPER] Lucro travado antecipadamente a ${early_sell_price:.2f}!")
                            break

        # 9. Apuração Final e Liquidação Oficial
        # Aguarda a vela fechar completamente (calculando o tempo real restante para evitar overshoot)
        now_utc_end = datetime.now(timezone.utc)
        current_elapsed = (now_utc_end.minute % 15) * 60 + now_utc_end.second
        time_to_close = max(0, 900 - current_elapsed)
        if time_to_close > 0:
            print(f"[*] Aguardando {time_to_close + 5}s até fechamento oficial e oráculo...")
            time.sleep(time_to_close + 5)

        official_winner = None
        winner_source = "KALSHI_OFFICIAL_ORACLE"

        if self.mode == "LIVE":
            settlement = self.client.get_market_settlement(ticker, max_retries=6)
            if settlement and settlement.get("result"):
                official_winner = settlement["result"].upper()
                print(f"\n    [🏛️ ORÁCULO OFICIAL KALSHI/PYTH]: Resultado oficial consolidado: {official_winner}")

        if not official_winner:
            # Fallback para spot Henry Hub de fechamento (estritamente maior para YES na Kalshi)
            final_spot = get_natgas_spot() or spot_now
            official_winner = "YES" if final_spot > strike_price else "NO"
            winner_source = "HENRY_HUB_SPOT_FALLBACK"

        # Cálculo financeiro
        if sold_early:
            payout = round(contracts_bought * early_sell_price, 2)
            cycle_pnl = round(payout - (contracts_bought * best_price), 2)
            res_str = "VITÓRIA (TAKE-PROFIT ANTECIPADO)"
        else:
            win = (official_winner == candidate_side.upper())
            payout = round(contracts_bought * 1.00, 2) if win else 0.00
            cycle_pnl = round(payout - (contracts_bought * best_price), 2)
            res_str = "VITÓRIA" if win else "DERROTA"

        # Atualiza saldo
        if self.mode == "LIVE":
            b_info = self.client.get_real_balance()
            self.balance = b_info.get("shard2_balance", self.balance)
        else:
            self.balance = round(self.balance + cycle_pnl, 2)

        self.clear_open_position()

        # Grava no Diário
        self.record_trade({
            "ticker": ticker,
            "side": candidate_side.upper(),
            "strike": strike_price,
            "spot_entry": spot_now,
            "entry_price": best_price,
            "contracts": contracts_bought,
            "sold_early": sold_early,
            "early_sell_price": early_sell_price,
            "winner": official_winner,
            "winner_source": winner_source,
            "result": res_str,
            "payout": payout,
            "pnl": cycle_pnl,
            "balance": self.balance,
            "timestamp": datetime.now().isoformat()
        })

        print(f"\n" + "=" * 80)
        print(f" [RESULTADO DESK 5]: {res_str} | P&L: {cycle_pnl:+.2f} USD | Saldo Shard 2: ${self.balance:.2f} USD")
        print("=" * 80)

    def record_trade(self, trade_data: dict):
        journal = {"mode": f"{self.mode}_NATGAS_15M", "current_balance": self.balance, "trades": []}
        if os.path.exists(JOURNAL_JSON):
            try:
                with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                    journal = json.load(f)
            except Exception:
                pass
        journal["trades"] = journal.get("trades", [])
        journal["trades"].append(trade_data)
        journal["current_balance"] = self.balance
        wins = sum(1 for t in journal["trades"] if t.get("pnl", 0) >= 0)
        losses = sum(1 for t in journal["trades"] if t.get("pnl", 0) < 0)
        total = len(journal["trades"])
        journal["wins"] = wins
        journal["losses"] = losses
        journal["win_rate"] = round(wins / total * 100, 1) if total > 0 else 0.0

        try:
            with open(JOURNAL_JSON, "w", encoding="utf-8") as f:
                json.dump(journal, f, indent=2)
        except Exception as e:
            print(f"[Erro ao gravar diário NatGas 15m]: {e}")

def main():
    print("=" * 80)
    print("  🔥 INICIANDO DESK 5: KALSHI NATURAL GAS 15-MINUTE ALGO TRADER")
    print(f"  Modo de Execução: {EXECUTION_MODE} | Shard de Risco: Shard 2")
    print(f"  Contrato: KXNATGAS15M | Deadband: 10.0 bps | Sweet-Spot: 450s")
    print("=" * 80)

    trader = KalshiNatGasTrader15M()
    while True:
        try:
            trader.run_cycle()
        except KeyboardInterrupt:
            print("\n[DESK 5 ENCERRADO PELO USUÁRIO]")
            break
        except Exception as e:
            print(f"\n[ERRO NO CICLO DO DESK 5]: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
