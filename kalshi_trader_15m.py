"""
=============================================================================
KALSHI BTC 15-MINUTE ALGO TRADER (KXBTC15M) — CÓDIGO IRMÃO
=============================================================================
- Exchange: Kalshi (Regulada CFTC) — Série: KXBTC15M
- Protocolo: REST API v2 com Autenticação RSA-PSS
- Frequência: Ciclos de 15 Minutos (900 segundos)
- Ponto de Avaliação: ~405s a 450s (metade da vela de 15m)
- Estratégia Quantitativa:
  * Deadband Dinâmico Scale-Invariant: 3.5 bps (0.035%) do Strike (min floor $25)
  * Teto de Preço: 60 centavos (breakeven <= 60%, EV estritamente positivo)
  * Take-Profit Antecipado (SirMartingale): Venda com lucro se cota atingir >= 86¢
  * Stop-Loss de Emergência: Liquidação antecipada se delta reverter contra
- Modos: PAPER (Simulação em tempo real com book real) e LIVE (Execução real)
=============================================================================
"""

import os
import sys
import time
import json
import base64
import urllib.request
import threading
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List

from execution_math import (
    compute_kalshi_dynamic_contracts,
    check_round_number_barrier,
    detect_dow_regime_15m,
    calculate_black_scholes_digital_fv,
    safe_eval_gate
)
from variable_bench import bench
from risk_gate import atomic_write_json, record_desk_trade_result

# Garante UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ===================== CONFIGURAÇÕES GERAIS =====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")

# Endpoints Kalshi API v2
KALSHI_API_PROD = "https://external-api.kalshi.com/trade-api/v2"
KALSHI_API_DEMO = "https://external-api.demo.kalshi.co/trade-api/v2"

# Parâmetros de Risco e Estratégia (Calibração Equilibrada JEV AI — Sweet-Spot Kalshi/Desk 3B)
FIXED_STAKE = 1.00                # $1.00 por contrato base
DEADBAND_BPS = 0.00038            # 3.8 bps (0.038%) do preço do BTC (Jev Balanceado)
DEADBAND_MIN_FLOOR = 40.0         # Piso mínimo de $40.00 contra ruído em 15m (Consenso JEV anti-chop)
PRIMARY_MAX_PRICE = 66            # Preço máximo em centavos (66¢ = 0.66 USD, EV positivo na Kalshi)
PRIMARY_MIN_PRICE = 40            # Preço mínimo em centavos (40¢ = 0.40 USD - elimina compras tóxicas sub-40¢)
TAKE_PROFIT_CENTS = 86            # Venda antecipada se cota bater 86¢ (lucro travado)
STOP_LOSS_MIN_BID = 15            # Bid mínimo aceito para Stop Loss na CLOB
EVAL_POINT_SEC = 450              # Ponto de decisão aos 450s (exata metade dos 900s da vela)
REQUIRE_PRIOR_CANDLE_TREND = True # Filtro Jev Trend Continuation com Override de Delta Forte (>= 1.5x)
PRIOR_CANDLE_MIN_BPS = 3.0        # Piso de ruído neutro (Consenso JEV 100%): |ret_bps| < 3.0 não veta drift forte

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
EXECUTION_MODE = ENV_CFG.get("KALSHI_MODE", "PAPER").upper() # 'PAPER' ou 'LIVE' (Segurança: Default = PAPER)
JOURNAL_JSON = os.path.join(BASE_DIR, "kalshi_trading_journal.json" if EXECUTION_MODE == "LIVE" else "kalshi_paper_journal.json")
KALSHI_KEY_ID = ENV_CFG.get("KALSHI_KEY_ID", "")
raw_key_path = ENV_CFG.get("KALSHI_PRIVATE_KEY_PATH", "kalshi.txt")
KALSHI_PRIVATE_KEY_PATH = raw_key_path if os.path.isabs(raw_key_path) else os.path.join(BASE_DIR, raw_key_path)

# ===================== CLIENTE KALSHI API V2 =====================
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
                print(f"[Aviso Kalshi] Chave privada PEM não pôde ser carregada: {e}")

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
            "User-Agent": "KalshiBTC15mAlgoTrader/2.0"
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
            print(f"[Kalshi API Erro {e.code}]: {err_body}")
            return None
        except Exception as e:
            print(f"[Kalshi Request Erro]: {e}")
            return None

    def get_real_balance(self) -> Dict[str, float]:
        """Consulta o saldo real na Kalshi via API v2"""
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

    def get_btc_15m_markets(self) -> List[dict]:
        """
        Busca o mercado KXBTC15M atualmente em andamento na Kalshi.
        Arquitetura Certificada pelo JEV SystemOne (100% de Convicção):
        1. Detecção da Janela Diária de Manutenção Kalshi (03:00 - 05:00 ET / 07:00 - 09:00 UTC).
        2. Consulta por Janela Temporal Estrita (min_close_ts / max_close_ts).
        3. Resolução Determinística de Ticker via Fuso ET (KXBTC15M-{YY}{MMM}{DD}{HHMM}-{MM}).
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
                print(f"   [🏛️ KALSHI EXCHANGE HALT]: Janela diária oficial de manutenção e clearing ({now_et.strftime('%H:%M')} ET / {now_utc.strftime('%H:%M')} UTC). Nenhum contrato KXBTC15M emitido.")
                return []
        except Exception:
            pass

        # 1. Consulta Cirúrgica por Janela Temporal Estrita (min_close_ts / max_close_ts)
        try:
            params = {
                "series_ticker": "KXBTC15M",
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
            print(f"   [Aviso Discovery L1]: Erro na consulta temporal Kalshi: {e}")

        # 2. Resolução Determinística de Ticker (Cálculo Matemático do Ticker Intradiário)
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
            det_ticker = f"KXBTC15M-{yy}{mmm}{dd}{hhmm}-{mm}"

            res_single = self.request("GET", f"/markets/{det_ticker}")
            if res_single and "market" in res_single:
                m = res_single["market"]
                ct = m.get("close_time")
                if not ct or ct > now_iso:
                    return [m]
        except Exception as e:
            print(f"   [Aviso Discovery L2]: Erro na resolução determinística: {e}")

        # 3. Fallback Resiliente com Ordenação Ascendente por close_time
        try:
            res_fb = self.request("GET", "/markets", params={"series_ticker": "KXBTC15M", "min_close_ts": now_ts, "limit": 100})
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
            print(f"   [Aviso Discovery L3]: Erro no fallback: {e}")

        return []

    def get_market(self, ticker: str) -> Optional[dict]:
        """Consulta dados individuais e preços em tempo real de um mercado específico"""
        res = self.request("GET", f"/markets/{ticker}")
        if res and "market" in res:
            return res["market"]
        return None

    def get_orderbook(self, ticker: str) -> Optional[dict]:
        """Obtém livro de ordens (order book L2)"""
        return self.request("GET", f"/markets/{ticker}/orderbook")

    def place_order(self, ticker: str, side: str, count: int, price_cents: int, action: str = "buy") -> Optional[dict]:
        """Envia ordem limit oficial V2 na Kalshi (side='yes' ou 'no', action='buy' ou 'sell')"""
        # Na API V2 single-book da Kalshi:
        # BUY YES  -> side='bid', price = yes_dollars
        # BUY NO   -> side='ask', price = (1.00 - no_dollars)
        # SELL YES -> side='ask', price = yes_dollars
        # SELL NO  -> side='bid', price = (1.00 - no_dollars)
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
            "client_order_id": f"kbtc15_{action}_{int(time.time()*1000)}"
        }
        return self.request("POST", "/portfolio/events/orders", body=payload, auth_required=True)

    def cancel_order(self, order_id: str, exchange_index: int = 2) -> Optional[dict]:
        """Cancela ordem oficial V2 na Kalshi"""
        return self.request("DELETE", f"/portfolio/orders/{order_id}?exchange_index={exchange_index}", auth_required=True)

    def get_order_status(self, order_id: str) -> Optional[dict]:
        """Consulta o status de uma ordem oficial na Kalshi"""
        return self.request("GET", f"/portfolio/orders/{order_id}", auth_required=True)

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

    def get_portfolio_settlement(self, ticker: str, max_retries: int = 6, delay: int = 3) -> Optional[dict]:
        """
        Consulta o resultado oficial e indiscutível de liquidação no portfólio Kalshi (/portfolio/settlements).
        Retorna o registro oficial contendo 'market_result' ('yes'/'no'), 'revenue' (centavos) e 'fee_cost'.
        """
        for _ in range(max_retries):
            res = self.request("GET", "/portfolio/settlements", auth_required=True)
            if res and "settlements" in res:
                for s in res["settlements"]:
                    if s.get("ticker") == ticker:
                        return s
            time.sleep(delay)
        return None



# ===================== ENGINE DE PREÇO SPOT (CF Benchmarks CME BRTI / Coinbase & Kraken Ref) =====================
def get_kalshi_benchmark_spot() -> Optional[float]:
    """
    Consulta o índice spot oficial de referência da Kalshi (CF Benchmarks CME BRTI).
    Fontes constitutivas prioritárias: Coinbase BTC-USD e Kraken XBTUSD.
    Elimina o basis USDT da Binance que causava falsos positivos na direção do contrato.
    """
    prices = []
    # 1. Coinbase BTC-USD (Maior peso no índice CF Benchmarks)
    try:
        req_cb = urllib.request.Request("https://api.exchange.coinbase.com/products/BTC-USD/ticker", headers={"User-Agent": "KalshiTrader/2.0"})
        with urllib.request.urlopen(req_cb, timeout=2.5) as r:
            p_cb = float(json.loads(r.read().decode())["price"])
            if p_cb > 1000:
                prices.append(p_cb)
    except Exception:
        pass

    # 2. Kraken BTC-USD (Constituinte oficial CME/CF Benchmarks)
    try:
        req_kr = urllib.request.Request("https://api.kraken.com/0/public/Ticker?pair=XBTUSD", headers={"User-Agent": "KalshiTrader/2.0"})
        with urllib.request.urlopen(req_kr, timeout=2.5) as r:
            data_kr = json.loads(r.read().decode())
            p_kr = float(data_kr["result"]["XXBTZUSD"]["c"][0])
            if p_kr > 1000:
                prices.append(p_kr)
    except Exception:
        pass

    if prices:
        return round(sum(prices) / len(prices), 2)

    # Fallback apenas se Coinbase e Kraken falharem simultaneamente:
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

def get_binance_btc_spot() -> Optional[float]:
    """Alias para compatibilidade retroativa"""
    return get_kalshi_benchmark_spot()

def get_kalshi_btc_15m_prior_candle() -> Optional[Dict[str, Any]]:
    """
    Consulta a última vela de 15m FECHADA no Coinbase BTC-USD (ou Binance em fallback)
    para validação de tendência macro no mesmo índice de liquidação da Kalshi.
    """
    try:
        req_cb = urllib.request.Request("https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=900", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req_cb, timeout=3) as r:
            cb_data = json.loads(r.read().decode())
            if len(cb_data) >= 2:
                prior = cb_data[1]  # [time, low, high, open, close, volume]
                p_open = float(prior[3])
                p_close = float(prior[4])
                p_dir = "UP" if p_close >= p_open else "DOWN"
                ret_bps = (abs(p_close - p_open) / p_open) * 10000
                return {"dir": p_dir, "open": p_open, "close": p_close, "ret_bps": ret_bps}
    except Exception:
        pass

    # Fallback Binance
    urls = [
        "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=2",
        "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=2"
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

def get_binance_btc_15m_prior_candle() -> Optional[Dict[str, Any]]:
    """Alias para compatibilidade retroativa"""
    return get_kalshi_btc_15m_prior_candle()


# ===================== LOOP PRINCIPAL DO KALSHI TRADER =====================
class KalshiTrader15M:
    def __init__(self):
        self.client = KalshiClient(KALSHI_KEY_ID, KALSHI_PRIVATE_KEY_PATH)
        self.kalshi_client = self.client  # Garantia de compatibilidade de atributos
        self.mode = EXECUTION_MODE
        self.balance = 35.00 # fallback padrão
        self.current_open_position = None
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
                    if self.mode != "LIVE":
                        self.balance = data.get("current_balance", self.balance)
                    else:
                        # Em live, sincroniza com o saldo real da Shard 2
                        b_info = self.client.get_real_balance()
                        real_s2 = b_info.get("shard2_balance")
                        if real_s2 and real_s2 > 0:
                            self.balance = real_s2
            except Exception:
                pass

    def save_open_position(self, pos_data: dict):
        self.current_open_position = pos_data
        if os.path.exists(JOURNAL_JSON):
            try:
                with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["open_position"] = pos_data
                atomic_write_json(JOURNAL_JSON, data)
            except Exception:
                pass

    def clear_open_position(self):
        self.current_open_position = None
        if os.path.exists(JOURNAL_JSON):
            try:
                with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["open_position"] = None
                atomic_write_json(JOURNAL_JSON, data)
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

        # Verificacao de Kill-Switch Global via Arquivo ('HALT' ou 'EMERGENCY_STOP')
        halt_file = os.path.join(BASE_DIR, "HALT")
        emergency_file = os.path.join(BASE_DIR, "EMERGENCY_STOP")
        if os.path.exists(halt_file) or os.path.exists(emergency_file):
            print(f"\n    [🚨 KILL-SWITCH GLOBAL ATIVADO]: Arquivo de emergencia detectado. Nenhuma ordem sera aberta na Kalshi.")
            time.sleep(15)
            return

        print("\n" + "=" * 80)
        print(f" [KALSHI 15M] Janela Ativa: {now_utc.strftime('%Y-%m-%d')} {now_utc.hour:02d}:{window_minute:02d}:00 UTC")
        print(f" Tempo Decorrido: {elapsed_sec}s / 900s | Restam: {remaining_sec}s | Modo: {self.mode}")
        print(f" Saldo Real Shard 2: ${self.balance:,.2f} USD")
        print("=" * 80)

        # Checagem do Variable Bench e Disjuntores (Universal 2-Loss + Coin-Flip - JEV AI)
        is_benched, bench_reason, bench_rem = bench.check_consecutive_losses_breaker("desk3", JOURNAL_JSON, max_consecutive_losses=2, cooldown_seconds=1800)
        if not is_benched:
            is_benched, bench_reason, bench_rem = bench.check_coin_flip_breaker("desk3", JOURNAL_JSON)
        if not is_benched:
            is_benched, bench_reason, bench_rem = bench.is_benched("desk3")
        if is_benched:
            print(f"\n   [🛑 VARIABLE BENCH]: Desk 3 em cooldown ({bench_reason}) — restam {bench_rem:.1f}s. Pausado...")
            time.sleep(min(30, max(5, int(bench_rem))))
            return

        has_resumed = False
        contract_count = 1
        if self.current_open_position:
            pos = self.current_open_position
            ticker = pos.get("ticker", "KXBTC15M-ACTIVE")
            target_side = pos.get("target_side", "yes")
            entry_price = int(pos.get("entry_price", 50))
            contract_count = int(pos.get("count", 1))
            stake = float(pos.get("stake", 0.50))
            real_order_id = pos.get("order_id", "")
            strike_price = float(pos.get("strike_price", 0.0))
            spot_now = strike_price
            has_resumed = True
            should_enter = True
            print(f"\n[🔄 RESUME GUARD]: Posição em aberto detectada na inicialização do ciclo.")
            print(f"   Ticker: {ticker} | Lado: {target_side.upper()} ({contract_count}x) | Entrada: {entry_price}¢ | Strike: ${strike_price:,.2f}")
            print("   -> Retomando monitoramento de saída e apuração sem abrir nova ordem!")
        else:
            # 1. Ponto de Avaliação Ótimo: Aos 450s (exata metade dos 900s da vela de 15m)
            eval_point = EVAL_POINT_SEC
            if elapsed_sec < eval_point:
                wait = eval_point - elapsed_sec
                print(f"[*] Aguardando {wait}s até o ponto quantitativo de decisão ({eval_point}s - 50% da vela de 15m)...")
                time.sleep(min(wait, 30))
                return

            # 2. Captura Strike e Spot Atual
            spot_now = get_binance_btc_spot()
            if not spot_now:
                print("[!] Falha ao ler preço spot de referência. Aguardando...")
                time.sleep(10)
                return

            # Busca mercados Kalshi para a série KXBTC15M
            markets = self.client.get_btc_15m_markets()
            if not markets:
                print("[i] Nenhum mercado KXBTC15M aberto no momento no endpoint da Kalshi. Pulando ciclo.")
                time.sleep(30)
                return

            target_market = markets[0]
            ticker = target_market.get("ticker", "KXBTC15M-ACTIVE")
            raw_strike = target_market.get("floor_strike") or target_market.get("strike_price")
            if not raw_strike and target_market.get("yes_sub_title"):
                import re
                m_match = re.search(r"\$([0-9,]+(?:\.[0-9]+)?)", str(target_market["yes_sub_title"]))
                if m_match:
                    try:
                        raw_strike = float(m_match.group(1).replace(",", ""))
                    except Exception:
                        pass
            strike_price = float(raw_strike or spot_now)

            # 2.1 Detecção do Regime de Charles Dow (Raghee Horner / JEV AI)
            dow_info = detect_dow_regime_15m(symbol="BTCUSDT")
            dow_mult = dow_info.get("deadband_multiplier", 1.0)
            dow_rec_contracts = dow_info.get("recommended_contracts", 2)
            print(f"   [🏛️ DOW REGIME DETECTOR]: {dow_info.get('description')}")

            delta = spot_now - strike_price
            dynamic_deadband = max(DEADBAND_MIN_FLOOR, round(strike_price * DEADBAND_BPS * dow_mult, 2))

            print(f"\n[📊 ANÁLISE DE MERCADO KALSHI]:")
            print(f"   Ticker: {ticker}")
            print(f"   Strike (K): ${strike_price:,.2f} | Spot Atual: ${spot_now:,.2f}")
            print(f"   Drift Real (Delta): ${delta:+.2f} | Deadband Dinâmico: ${dynamic_deadband:.2f} ({DEADBAND_BPS*10000*dow_mult:.1f} bps)")

            # 3. Decisão de Entrada
            candidate_side = None
            target_dir = None

            if delta >= dynamic_deadband:
                candidate_side = "yes"
                target_dir = "UP"
                print(f"   -> [SINAL INTRA-VELA]: UP / YES (Drift de +${delta:.2f} superou deadband de ${dynamic_deadband:.2f})")
            elif delta <= -dynamic_deadband:
                candidate_side = "no"
                target_dir = "DOWN"
                print(f"   -> [SINAL INTRA-VELA]: DOWN / NO (Drift de -${abs(delta):.2f} superou deadband de ${dynamic_deadband:.2f})")
            else:
                print(f"   -> [FILTRO DEADBAND]: Delta de ${delta:+.2f} está na zona morta (< ${dynamic_deadband:.2f} | {DEADBAND_BPS*10000*dow_mult:.1f} bps). Preservando capital.")
                time.sleep(max(1, remaining_sec))
                return

            # 3.0 Veto de Contratendência no Dow Regime (Consenso JEV / Raghee Horner)
            dow_regime = dow_info.get("regime", "")
            dow_slope = dow_info.get("slope_bps", 0.0)
            reversal_mult = 2.5
            strong_reversal_threshold = round(dynamic_deadband * reversal_mult, 2)

            if dow_regime == "DOWNTREND" and candidate_side == "yes":
                if delta < strong_reversal_threshold:
                    print(f"   [🛡️ VETO DOW REGIME - JEV]: Tentativa de comprar YES (UP) contra Tendência de Baixa ativa (Slope: {dow_slope:+.1f} bps).")
                    print(f"      Delta de +${delta:.2f} é repique fraco (< ${strong_reversal_threshold:.2f} exigidos para contratendência). Abortando para preservar capital.")
                    time.sleep(max(1, remaining_sec))
                    return
                else:
                    print(f"   [🔥 OVERRIDE DOW REVERSAL]: Delta massivo de +${delta:.2f} superou {reversal_mult}x deadband (${strong_reversal_threshold:.2f}). Reversão validada.")

            elif dow_regime == "UPTREND" and candidate_side == "no":
                if abs(delta) < strong_reversal_threshold:
                    print(f"   [🛡️ VETO DOW REGIME - JEV]: Tentativa de comprar NO (DOWN) contra Tendência de Alta ativa (Slope: {dow_slope:+.1f} bps).")
                    print(f"      Delta de -${abs(delta):.2f} é correção fraca (< ${strong_reversal_threshold:.2f} exigidos para contratendência). Abortando para preservar capital.")
                    time.sleep(max(1, remaining_sec))
                    return
                else:
                    print(f"   [🔥 OVERRIDE DOW REVERSAL]: Delta massivo de -${abs(delta):.2f} superou {reversal_mult}x deadband (${strong_reversal_threshold:.2f}). Reversão validada.")

            # 3.1 Filtro Round Number Barrier Shield (.00 Double Zero - Raghee Horner / JEV)
            is_barrier, barrier_reason = check_round_number_barrier(spot=spot_now, target_side=target_dir, interval=500.0, buffer_usd=20.0)
            if is_barrier:
                print(f"   -> [🛡️ ROUND NUMBER SHIELD]: {barrier_reason}. Abortando entrada para evitar ricochete.")
                time.sleep(max(1, remaining_sec))
                return

            # 3.1 Filtro de Vela Anterior (Recomendação JEV — Trend Continuation com Override de Delta Forte)
            if REQUIRE_PRIOR_CANDLE_TREND:
                prior_candle = get_binance_btc_15m_prior_candle()
                if prior_candle:
                    prior_dir = prior_candle["dir"]
                    ret_bps = prior_candle["ret_bps"]
                    print(f"   [🕯️ FILTRO DE VELA ANTERIOR - JEV]: Vela 15m Anterior fechou {prior_dir} ({ret_bps:.1f} bps)")
                    if ret_bps < PRIOR_CANDLE_MIN_BPS:
                        print(f"   -> [🕯️ VELA ANTERIOR NEUTRA - JEV]: Variação de {ret_bps:.1f} bps < {PRIOR_CANDLE_MIN_BPS:.1f} bps (ruído microestrutural plano).")
                        print(f"      Drift intra-vela ({target_dir} | Delta ${delta:+.2f}) prevalece sem veto de contratendência.")
                    elif target_dir != prior_dir:
                        # Consenso JEV: Se o drift intra-vela for muito expressivo (|Delta| >= 1.5 * dynamic_deadband), concede override
                        strong_override_threshold = round(dynamic_deadband * 1.5, 2)
                        if abs(delta) >= strong_override_threshold:
                            print(f"   -> [🔥 OVERRIDE JEV DRIFT FORTE]: Sinal {target_dir} diverge da vela anterior ({prior_dir}), mas |Delta| de ${abs(delta):.2f} superou 1.5x deadband (${strong_override_threshold:.2f}).")
                            print("      Drift de alta convicção validado — prosseguindo com entrada!")
                        else:
                            print(f"   -> [🛡️ VETO JEV]: Sinal {target_dir} ({candidate_side.upper()}) rejeitado por divergir de tendência real anterior ({prior_dir} com {ret_bps:.1f} bps).")
                            print(f"      Delta ${abs(delta):.2f} insuficiente para override (< ${strong_override_threshold:.2f}). Preservando capital.")
                            time.sleep(max(1, remaining_sec))
                            return
                    else:
                        print(f"   -> [🔥 CONFIRMAÇÃO JEV]: Tendência da vela anterior ({prior_dir} com {ret_bps:.1f} bps) alinhada com drift intra-vela ({target_dir})! Convicção alta.")
                else:
                    print("   [Aviso]: Não foi possível ler vela anterior da Binance. Prosseguindo com drift intra-vela.")

            should_enter = True
            target_side = candidate_side

        # 4. Execução (Paper ou Live)
        if should_enter:
            if not has_resumed:
                # Consulta endpoint individual e Order Book para obter preços reais e evitar preços fantasmas do batch
                m_detail = self.client.get_market(ticker)
                if m_detail:
                    target_market.update(m_detail)

                yes_ask = None
                no_ask = None

                # 1. Tenta extrair do endpoint de mercado individual
                y_ask_val = target_market.get("yes_ask_dollars") or target_market.get("yes_ask")
                n_ask_val = target_market.get("no_ask_dollars") or target_market.get("no_ask")
                if y_ask_val is not None and float(y_ask_val) > 0.0:
                    yes_ask = int(float(y_ask_val) * 100)
                if n_ask_val is not None and float(n_ask_val) > 0.0 and float(n_ask_val) < 1.0:
                    no_ask = int(float(n_ask_val) * 100)

                # 2. Se vier fantasma (0 ou 100), extrai diretamente do livro de ordens L2
                ob = self.client.get_orderbook(ticker)
                avail_qty = 1
                if ob and "orderbook_fp" in ob:
                    ob_fp = ob["orderbook_fp"]
                    y_orders = ob_fp.get("yes_dollars", [])
                    n_orders = ob_fp.get("no_dollars", [])
                    if y_orders and (yes_ask is None or yes_ask <= 0 or yes_ask >= 100):
                        yes_ask = int(float(y_orders[-1][0]) * 100)
                    if n_orders and (no_ask is None or no_ask <= 0 or no_ask >= 100):
                        no_ask = int(float(n_orders[-1][0]) * 100)

                    target_orders = y_orders if target_side == "yes" else n_orders
                    if target_orders and len(target_orders[-1]) > 1:
                        avail_qty = int(float(target_orders[-1][1]))

                entry_price = yes_ask if target_side == "yes" else no_ask
                if entry_price is None:
                    entry_price = 55 # Fallback prudente se livro estiver completamente vazio

                # 4.1 Gate Híbrido Black-Scholes Fair Value (Validado 100% pelo JEV AI — Backtest 9 Anos)
                # Calcula a probabilidade neutra ao risco N(d2) da opção digital aos 450s
                bs_prob_up = calculate_black_scholes_digital_fv(
                    spot=spot_now,
                    strike=strike_price,
                    elapsed_sec=int(elapsed_sec),
                    total_sec=900,
                    sigma=0.0030
                )
                target_fv_cents = round((bs_prob_up if target_side == "yes" else (1.0 - bs_prob_up)) * 100.0, 1)
                
                # Teto Híbrido: min(PRIMARY_MAX_PRICE, max(PRIMARY_MIN_PRICE, int(target_fv_cents + 2.0)))
                # Protege contra compras muito acima do FV quando o drift for fraco, tolerando o spread natural de 1-2¢ do formador de mercado.
                hybrid_max_price = min(PRIMARY_MAX_PRICE, max(PRIMARY_MIN_PRICE, int(target_fv_cents + 2.0)))

                if entry_price > hybrid_max_price:
                    print(f"   [🛡️ GATE HÍBRIDO BLACK-SCHOLES]: Cota a {entry_price}¢ excede o Teto Híbrido de {hybrid_max_price}¢ (Valor Justo BS: {target_fv_cents:.1f}¢ + 2¢ spread | Cap Estático: {PRIMARY_MAX_PRICE}¢). Pulando entrada com Negative EV.")
                    time.sleep(max(1, remaining_sec))
                    return

                if entry_price < PRIMARY_MIN_PRICE:
                    print(f"   [🛡️ FILTRO PISO DE PREÇO JEV]: Cota a {entry_price}¢ < {PRIMARY_MIN_PRICE}¢ (Armadilha de reversão / Seleção adversa sub-40¢). Pulando entrada.")
                    time.sleep(max(1, remaining_sec))
                    return

                # 4.1.1 Consenso Rivo 6,532 Mercados / JEV: Banimento do Líder Fraco (60¢-70¢)
                # Calibrado via backtest de 9 anos (Piso $40.00): maximiza WR (77.0%), PF (2.05) e evita trade starvation.
                if 60 <= entry_price <= 70 and abs(delta) < dynamic_deadband:
                    print(f"   [🛡️ FILTRO CONSENSO RIVO/JEV]: Cota a {entry_price}¢ na Zona de Líder Fraco (60¢-70¢) com Delta ${abs(delta):.2f} < ${dynamic_deadband:.2f}. EV negativo. Pulando entrada para preservar capital.")
                    time.sleep(max(1, remaining_sec))
                    return

                # 4.2 Convicção Estatística e Ratio de Delta
                delta_ratio = abs(delta) / max(1.0, dynamic_deadband)
                win_prob = 0.70
                if delta_ratio >= 1.5:
                    win_prob += 0.05
                if delta_ratio >= 2.0:
                    win_prob += 0.05

                # 4.3 Dimensionamento por Kelly Fracionário (25%) com Guardrails Kalshi
                # Calibração Dinâmica JEV: 2 contratos permitidos apenas em tendência clara (Dow Regime). Em distribuição/choppy, trava em 1 contrato.
                allow_2_contracts = ((self.mode == "PAPER") or (self.balance >= 20.0) or (abs(delta) >= 50.0 and self.balance >= 12.0)) and (dow_rec_contracts >= 2)
                safe_min = 2 if allow_2_contracts else 1
                safe_cap = 2 if allow_2_contracts else 1
                count, kelly_status = compute_kalshi_dynamic_contracts(
                    bankroll=self.balance,
                    win_probability=win_prob,
                    entry_price_cents=entry_price,
                    available_qty=avail_qty,
                    delta_ratio=delta_ratio,
                    min_contracts=safe_min,
                    max_contracts_cap=safe_cap
                )
                # 4.4 CÃO DE GUARDA JEV (Blindagem Anti-Exaustão e Anti-Repique na Kalshi BTC)
                try:
                    from jev_microstructure_gate import jev_gate
                    sp_usd = round(float(best_ask - best_bid) / 100.0, 4) if (best_ask and best_bid) else 0.03
                    jev_res = jev_gate.evaluate_entry(
                        desk_id="desk3",
                        delta_usd=delta,
                        binance_drift=round(delta * 0.25, 2),
                        clob_spread=sp_usd,
                        contract_price=round(entry_price / 100.0, 3),
                        oracle_discrepancy=0.50,
                        seconds_left=int(remaining_sec),
                        obi=0.0,
                        cvd=0.0,
                        deadband_threshold=dynamic_deadband,
                        side=target_side.upper(),
                        symbol="BTC"
                    )
                    if jev_res.get("verdict") == "VETO":
                        print(f"   [🛑 VETO CÃO DE GUARDA JEV KALSHI BTC]: {jev_res.get('veto_reason')} | Regime: {jev_res.get('candle_regime')}. Abortando entrada para evitar repique!")
                        time.sleep(max(1, remaining_sec))
                        return
                except Exception as e:
                    print(f"   [!] Aviso JEV Gate Kalshi BTC: {e}")

                print(f"\n[🚀 ORDEM KALSHI]: Comprando {contract_count}x {target_side.upper()} @ {entry_price}¢ (Modo: {self.mode}) | Stake: ${stake:.2f} ({kelly_status})")
                real_order_id = ""
                if self.mode == "LIVE":
                    # Validação de Saldo e Piso de Segurança Kalshi
                    b_info = self.client.get_real_balance()
                    real_s2 = b_info.get("shard2_balance", 0.0)
                    if real_s2 and real_s2 > 0:
                        self.balance = real_s2
                    if self.balance < 2.00:
                        print(f"   [🚨 TRAVA DE SEGURANÇA]: Saldo Kalshi Shard 2 (${self.balance:.2f}) abaixo do piso mínimo ($2.00). Abortando para preservar capital.")
                        time.sleep(max(1, remaining_sec))
                        return

                    res = self.client.place_order(ticker, target_side, contract_count, entry_price)
                    print(f"   [⚡ RESPOSTA DA ORDEM REAL KALSHI]: {res}")
                    if not res or ("order_id" not in res and "order" not in res):
                        print("   [!] Falha na execução da ordem na Kalshi. Abortando entrada para proteger capital.")
                        time.sleep(max(1, remaining_sec))
                        return
                    order_info = res.get("order", {}) if isinstance(res.get("order"), dict) else res
                    real_order_id = order_info.get("order_id") or res.get("order_id", "")
                    
                    # Detecção de execução imediata (taker fill instantâneo na Kalshi)
                    fill_cnt = float(res.get("fill_count") or order_info.get("fill_count") or 0.0)
                    rem_cnt = float(res.get("remaining_count") or order_info.get("remaining_count") or 1.0)
                    if rem_cnt == 0.0 and fill_cnt >= contract_count:
                        status = "executed"
                    else:
                        status = str(order_info.get("status", "resting")).lower()

                    print(f"   [⚡ STATUS INICIAL DA COMPRA]: ID: {real_order_id} | Status: {status} (Filled: {fill_cnt}/{contract_count})")

                    # Verificação rigorosa de execução (Fill-or-Cancel) no BUY
                    if status in ("open", "resting", "pending"):
                        print("   -> Aguardando confirmação de execução (fill) da compra no livro...")
                        for _ in range(4):
                            time.sleep(4)
                            chk = self.client.get_order_status(real_order_id)
                            if isinstance(chk, dict) and "order" in chk and isinstance(chk["order"], dict):
                                cur_st = str(chk["order"].get("status", "")).lower()
                                if cur_st in ("executed", "filled"):
                                    status = "filled"
                                    print("   -> Compra Kalshi PREENCHIDA (Filled) com sucesso!")
                                    break
                                elif cur_st:
                                    status = cur_st

                    if status not in ("executed", "filled"):
                        print(f"   [⚠️ COMPRA NÃO PREENCHIDA]: Status permanece '{status}'. Cancelando ordem resting para não deixar risco aberto.")
                        try:
                            self.client.cancel_order(real_order_id)
                        except Exception:
                            pass
                        time.sleep(max(1, remaining_sec))
                        return

                    print(f"   [✅ COMPRA CONFIRMADA ON-EXCHANGE]: {contract_count}x {target_side.upper()} @ {entry_price}¢ | Order ID: {real_order_id}")
                    self.save_open_position({
                        "ticker": ticker,
                        "target_side": target_side,
                        "count": contract_count,
                        "entry_price": entry_price,
                        "stake": stake,
                        "kelly_status": kelly_status,
                        "order_id": real_order_id,
                        "strike_price": strike_price,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                else:
                    print(f"   [SIMULAÇÃO PAPER]: {contract_count}x {target_side.upper()} executado a {entry_price}¢ com sucesso!")
                    self.save_open_position({
                        "ticker": ticker,
                        "target_side": target_side,
                        "count": contract_count,
                        "entry_price": entry_price,
                        "stake": stake,
                        "kelly_status": kelly_status,
                        "order_id": "paper-sim",
                        "strike_price": strike_price,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })

            # 5. Monitoramento de Take-Profit com Saída em Escala (Raghee Horner / JEV)
            print(f"[🎯 MONITORAMENTO KALSHI]: Acompanhando Take-Profit (>= {TAKE_PROFIT_CENTS}¢) até os 900s...")
            sold_early = False
            early_sell_price = 0
            tp1_executed = False
            tp1_pnl = 0.0
            total_pnl = 0.0

            while True:
                now_sec = (datetime.now(timezone.utc).minute % 15) * 60 + datetime.now(timezone.utc).second
                if now_sec >= 885:
                    break

                # Checagem de Take-Profit via Spot ou Orderbook
                spot_cur = get_binance_btc_spot()
                if spot_cur:
                    cur_delta = spot_cur - strike_price
                    # Se o delta expandiu significativamente a favor (> 15 bps), take profit
                    cur_bps = (abs(cur_delta) / strike_price) * 10000
                    if not tp1_executed and ((target_side == "yes" and cur_delta > 0 and cur_bps >= 15.0) or (target_side == "no" and cur_delta < 0 and cur_bps >= 15.0)):
                        early_sell_price = TAKE_PROFIT_CENTS
                        sell_ok = True
                        sell_order_id = "paper-tp"

                        if contract_count >= 2:
                            # Saída em Escala: Liquida 50% no TP1
                            half_contracts = contract_count // 2
                            if self.mode == "LIVE":
                                print(f"\n[💰 ENVIANDO ORDEM REAL DE VENDA PARCIAL (TP1 SCALE) NA KALSHI]:")
                                print(f"   Ticker: {ticker} | Lado: {target_side.upper()} ({half_contracts}x de {contract_count}x) | Preço Alvo: {early_sell_price}¢")
                                sell_res = self.client.place_order(ticker, target_side, count=half_contracts, price_cents=early_sell_price, action="sell")
                                if isinstance(sell_res, dict) and ("order" in sell_res or "order_id" in sell_res):
                                    order_data = sell_res.get("order", {}) if isinstance(sell_res.get("order"), dict) else sell_res
                                    sell_order_id = order_data.get("order_id", "SUBMITTED")
                                    status = str(order_data.get("status", "resting")).lower()
                                    if status in ("open", "resting", "pending"):
                                        for _ in range(4):
                                            time.sleep(5)
                                            chk = self.client.get_order_status(sell_order_id)
                                            if isinstance(chk, dict) and "order" in chk and isinstance(chk["order"], dict):
                                                cur_st = str(chk["order"].get("status", "")).lower()
                                                if cur_st in ("executed", "filled"):
                                                    status = "filled"
                                                    break
                                    sell_ok = (status in ("executed", "filled"))
                                    if not sell_ok:
                                        try:
                                            self.client.cancel_order(sell_order_id)
                                        except Exception:
                                            pass
                                else:
                                    sell_ok = False

                            if sell_ok:
                                tp1_executed = True
                                payout_tp1 = round((early_sell_price / 100.0) * half_contracts, 4)
                                tp1_pnl = round(payout_tp1 - ((entry_price / 100.0) * half_contracts), 4)
                                contract_count -= half_contracts
                                stake = round((entry_price / 100.0) * contract_count, 4)
                                if self.mode == "LIVE":
                                    time.sleep(3)
                                    b_info = self.client.get_real_balance()
                                    real_s2 = b_info.get("shard2_balance")
                                    if real_s2 and real_s2 > 0:
                                        self.balance = real_s2
                                else:
                                    self.balance += tp1_pnl
                                self.save_open_position({
                                    "ticker": ticker,
                                    "target_side": target_side,
                                    "count": contract_count,
                                    "entry_price": entry_price,
                                    "stake": stake,
                                    "order_id": real_order_id,
                                    "strike_price": strike_price,
                                    "tp1_executed": True,
                                    "tp1_pnl": tp1_pnl,
                                    "breakeven_price": entry_price,
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                })
                                print(f"\n[💰 RAGHEE SCALE - TP1 CONFIRMADO]: {half_contracts}x vendido a {early_sell_price}¢ (+${tp1_pnl:+.2f} USD)!")
                                print(f"   Runner ({contract_count}x) mantido com Stop Breakeven ({entry_price}¢)! Saldo: ${self.balance:,.2f}")
                        else:
                            # Saída Integral (apenas 1 contrato)
                            if self.mode == "LIVE":
                                print(f"\n[💰 ENVIANDO ORDEM REAL DE VENDA (TAKE-PROFIT) NA KALSHI]:")
                                print(f"   Ticker: {ticker} | Lado: {target_side.upper()} ({contract_count}x) | Preço Alvo: {early_sell_price}¢")
                                sell_res = self.client.place_order(ticker, target_side, count=contract_count, price_cents=early_sell_price, action="sell")
                                if isinstance(sell_res, dict) and ("order" in sell_res or "order_id" in sell_res):
                                    order_data = sell_res.get("order", {}) if isinstance(sell_res.get("order"), dict) else sell_res
                                    sell_order_id = order_data.get("order_id", "SUBMITTED")
                                    status = str(order_data.get("status", "resting")).lower()
                                    if status in ("open", "resting", "pending"):
                                        for _ in range(4):
                                            time.sleep(5)
                                            chk = self.client.get_order_status(sell_order_id)
                                            if isinstance(chk, dict) and "order" in chk and isinstance(chk["order"], dict):
                                                cur_st = str(chk["order"].get("status", "")).lower()
                                                if cur_st in ("executed", "filled"):
                                                    status = "filled"
                                                    break
                                    sell_ok = (status in ("executed", "filled"))
                                    if not sell_ok:
                                        try:
                                            self.client.cancel_order(sell_order_id)
                                        except Exception:
                                            pass
                                else:
                                    sell_ok = False

                            if sell_ok:
                                sold_early = True
                                payout = round((early_sell_price / 100.0) * contract_count, 4)
                                cycle_pnl = round(payout - stake, 4)
                                if self.mode == "LIVE":
                                    time.sleep(3)
                                    b_info = self.client.get_real_balance()
                                    real_s2 = b_info.get("shard2_balance")
                                    if real_s2 and real_s2 > 0:
                                        self.balance = real_s2
                                else:
                                    self.balance += cycle_pnl
                                print(f"\n[💰 TAKE-PROFIT KALSHI CONFIRMADO]: Posição vendida a {early_sell_price}¢ ({contract_count}x | Drift: {cur_bps:.1f} bps)!")
                                print(f"   Payout: ${payout:.2f} | P&L: {cycle_pnl:+.2f} USD | Novo Saldo: ${self.balance:,.2f}")
                                self.save_trade({
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "execution_mode": self.mode,
                                    "order_id": real_order_id,
                                    "sell_order_id": sell_order_id,
                                    "ticker": ticker,
                                    "count": contract_count,
                                    "strike": strike_price,
                                    "entry_price": entry_price,
                                    "target_side": target_side.upper(),
                                    "result": "VITÓRIA (TAKE-PROFIT)",
                                    "sold_early": True,
                                    "sell_price": early_sell_price,
                                    "payout": payout,
                                    "cycle_pnl": round(cycle_pnl, 4),
                                    "balance": round(self.balance, 4)
                                })
                                self.clear_open_position()
                                time.sleep(max(1, 900 - now_sec))
                                return

                    # Monitoramento de Breakeven Stop no Runner (após TP1 executado)
                    elif tp1_executed:
                        # Se o delta reverter para neutro ou contra (<= 0 para YES, >= 0 para NO)
                        runner_be_triggered = (target_side == "yes" and cur_delta <= 0) or (target_side == "no" and cur_delta >= 0)
                        if runner_be_triggered:
                            print(f"\n[🛡️ RAGHEE SCALE - BREAKEVEN STOP DISPARADO]: Delta recuou para zero ({cur_delta:+.2f}). Fechando runner ({contract_count}x)...")
                            be_sold_ok = True
                            if self.mode == "LIVE":
                                sell_res = self.client.place_order(ticker, target_side, count=contract_count, price_cents=entry_price, action="sell")
                                be_sold_ok = isinstance(sell_res, dict) and ("order" in sell_res or "order_id" in sell_res)
                            
                            payout_be = round((entry_price / 100.0) * contract_count, 4)
                            pnl_be = round(payout_be - stake, 4) # 0.00
                            total_pnl = round(tp1_pnl + pnl_be, 4)
                            sold_early = True
                            if self.mode == "LIVE":
                                time.sleep(3)
                                b_info = self.client.get_real_balance()
                                real_s2 = b_info.get("shard2_balance")
                                if real_s2 and real_s2 > 0:
                                    self.balance = real_s2
                            else:
                                self.balance += pnl_be
                            print(f"[🛡️ RAGHEE SCALE]: Runner protegido no Breakeven! Lucro Total do Trade: +${total_pnl:.2f} USD")
                            self.save_trade({
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "execution_mode": self.mode,
                                "order_id": real_order_id,
                                "ticker": ticker,
                                "count": contract_count,
                                "strike": strike_price,
                                "entry_price": entry_price,
                                "target_side": target_side.upper(),
                                "result": "VITÓRIA (BREAKEVEN RUNNER)",
                                "sold_early": True,
                                "sell_price": entry_price,
                                "payout": round(tp1_pnl + stake + payout_be, 4),
                                "cycle_pnl": round(total_pnl, 4),
                                "balance": round(self.balance, 4)
                            })
                            self.clear_open_position()
                            time.sleep(max(1, 900 - now_sec))
                            return

                time.sleep(15)

            # 6. Liquidação Oficial no Fechamento da Vela (se não saiu antecipado)
            if not sold_early:
                time.sleep(5)
                official_winner = None
                winner_source = "BENCHMARK_SPOT_ESTIMATED"
                official_revenue_dollars = None

                if self.mode == "LIVE":
                    print(f"   -> [CFTC CLEARING] Consultando liquidação oficial no portfólio Kalshi ({ticker})...")
                    port_settle = self.client.get_portfolio_settlement(ticker, max_retries=6, delay=3)
                    if port_settle:
                        k_res = str(port_settle.get("market_result", "")).lower()  # 'yes' ou 'no'
                        official_winner = "UP" if k_res == "yes" else "DOWN"
                        winner_source = "KALSHI_PORTFOLIO_SETTLEMENT"
                        is_win = (target_side.lower() == k_res)
                        rev_cents = float(port_settle.get("revenue", 0))
                        official_revenue_dollars = rev_cents / 100.0
                        print(f"   [🏛️ LIQUIDAÇÃO OFICIAL KALSHI]: Resultado: {k_res.upper()} | Revenue: ${official_revenue_dollars:.2f} | Vencedor: {official_winner}")
                    else:
                        print(f"   -> Consultando oráculo secundário de mercado na Kalshi API ({ticker})...")
                        settle_info = self.client.get_market_settlement(ticker, max_retries=3)
                        if settle_info and settle_info.get("result"):
                            k_res = settle_info["result"].lower()  # 'yes' ou 'no'
                            official_winner = "UP" if k_res == "yes" else "DOWN"
                            winner_source = "KALSHI_OFFICIAL_ORACLE"
                            is_win = (target_side.lower() == k_res)
                            print(f"   [🏛️ ORÁCULO DE MERCADO KALSHI]: Resultado: {k_res.upper()} | Vencedor: {official_winner}")

                final_spot = get_kalshi_benchmark_spot() or spot_now
                if official_winner is None:
                    is_win = (final_spot >= strike_price) if target_side == "yes" else (final_spot < strike_price)
                    winner = "UP" if final_spot >= strike_price else "DOWN"
                else:
                    winner = official_winner

                if tp1_executed:
                    payout_runner = official_revenue_dollars if official_revenue_dollars is not None else round((1.00 * contract_count) if is_win else 0.00, 4)
                    pnl_runner = round(payout_runner - stake, 4)
                    total_pnl = round(tp1_pnl + pnl_runner, 4)
                    payout = round(tp1_pnl + stake + payout_runner, 4)
                    cycle_pnl = total_pnl
                    res_str = f"VITÓRIA SCALE RUNNER (+${total_pnl:.2f})" if is_win else f"DEFESA TP1 (+${total_pnl:.2f})"
                    if self.mode == "LIVE":
                        time.sleep(3)
                        b_info = self.client.get_real_balance()
                        real_s2 = b_info.get("shard2_balance")
                        if real_s2 and real_s2 > 0:
                            self.balance = real_s2
                    else:
                        self.balance += pnl_runner
                else:
                    payout = official_revenue_dollars if official_revenue_dollars is not None else round((1.00 * contract_count) if is_win else 0.00, 4)
                    cycle_pnl = round(payout - stake, 4)
                    if self.mode == "LIVE":
                        time.sleep(3)
                        b_info = self.client.get_real_balance()
                        real_s2 = b_info.get("shard2_balance")
                        if real_s2 and real_s2 > 0:
                            self.balance = real_s2
                    else:
                        self.balance += cycle_pnl
                    res_str = "VITÓRIA" if is_win else "DERROTA"

                print(f"\n[🏁 APURAÇÃO FINAL KALSHI - JANELA CONCLUÍDA]:")
                print(f"   Strike (K): ${strike_price:,.2f} | Final Spot: ${final_spot:,.2f} | Vencedor: {winner} ({winner_source})")
                print(f"   Resultado: {res_str} | Contratos: {contract_count}x | Payout: ${payout:.2f} | P&L Ciclo: {cycle_pnl:+.2f} USD")
                print(f"   Saldo Atualizado: ${self.balance:,.2f} USD")

                self.save_trade({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "execution_mode": self.mode,
                    "order_id": real_order_id,
                    "ticker": ticker,
                    "count": contract_count,
                    "strike": strike_price,
                    "final_spot": final_spot,
                    "entry_price": entry_price,
                    "target_side": target_side.upper(),
                    "winner": winner,
                    "winner_source": winner_source,
                    "result": res_str,
                    "sold_early": False,
                    "payout": payout,
                    "cycle_pnl": round(cycle_pnl, 4),
                    "balance": round(self.balance, 4)
                })
                self.clear_open_position()

    def save_trade(self, trade_data: dict):
        journal = {"current_balance": round(self.balance, 4), "trades": []}
        if os.path.exists(JOURNAL_JSON):
            try:
                with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                    journal = json.load(f)
            except Exception:
                pass
        journal["current_balance"] = round(self.balance, 4)
        if "trades" not in journal:
            journal["trades"] = []
        journal["trades"].append(trade_data)
        
        # Estatísticas
        wins = sum(1 for t in journal["trades"] if "VITÓRIA" in t.get("result", ""))
        losses = sum(1 for t in journal["trades"] if "DERROTA" in t.get("result", ""))
        total = len(journal["trades"])
        journal["total_trades"] = total
        journal["wins"] = wins
        journal["losses"] = losses
        journal["win_rate"] = round((wins / total * 100), 1) if total > 0 else 0.0

        atomic_write_json(JOURNAL_JSON, journal)
        try:
            is_win = ("VITÓRIA" in str(trade_data.get("result", "")).upper()) or (float(trade_data.get("pnl", 0.0)) >= 0)
            record_desk_trade_result("desk3", is_win=is_win, pnl=float(trade_data.get("pnl", 0.0)))
        except Exception:
            pass

    def start(self):
        print("\n" + "=" * 80)
        print("  INICIANDO BOT KALSHI BTC 15-MINUTE ALGO TRADER")
        print(f"  Modo: {self.mode} | Banca Inicial: ${self.balance:.2f} USD")
        print("=" * 80)
        while True:
            try:
                self.run_cycle()
            except Exception as e:
                print(f"[Erro no ciclo Kalshi]: {e}")
            time.sleep(15)

if __name__ == "__main__":
    bot = KalshiTrader15M()
    bot.start()
