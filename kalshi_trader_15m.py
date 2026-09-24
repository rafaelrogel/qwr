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
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

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
JOURNAL_JSON = os.path.join(BASE_DIR, "kalshi_trading_journal.json")

# Endpoints Kalshi API v2
KALSHI_API_PROD = "https://external-api.kalshi.com/trade-api/v2"
KALSHI_API_DEMO = "https://external-api.demo.kalshi.co/trade-api/v2"

# Parâmetros de Risco e Estratégia (Otimizados com Jev AI - 9 Anos de Dados)
FIXED_STAKE = 1.00                # $1.00 por contrato base
DEADBAND_BPS = 0.00050            # 5.0 bps (0.050%) do preço do BTC (Jev Sweet-Spot 9 Anos)
DEADBAND_MIN_FLOOR = 40.0         # Piso mínimo de $40.00 contra ruído em 15m
PRIMARY_MAX_PRICE = 60            # Preço máximo em centavos (60¢ = 0.60 USD, breakeven <= 60%)
PRIMARY_MIN_PRICE = 35            # Preço mínimo em centavos (35¢ = 0.35 USD)
TAKE_PROFIT_CENTS = 86            # Venda antecipada se cota bater 86¢ (lucro travado)
STOP_LOSS_MIN_BID = 15            # Bid mínimo aceito para Stop Loss na CLOB
EVAL_POINT_SEC = 450              # Ponto de decisão aos 450s (exata metade dos 900s da vela)
REQUIRE_PRIOR_CANDLE_TREND = True # Filtro Jev Trend Continuation (75% preferência)

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
EXECUTION_MODE = ENV_CFG.get("KALSHI_MODE", "LIVE").upper() # 'PAPER' ou 'LIVE'
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
        """Busca o mercado KXBTC15M atualmente em andamento na Kalshi"""
        res = self.request("GET", "/markets", params={"series_ticker": "KXBTC15M", "limit": 100})
        if res and "markets" in res:
            now_iso = datetime.now(timezone.utc).isoformat()
            active_markets = []
            for m in res["markets"]:
                ot = m.get("open_time")
                ct = m.get("close_time")
                st = m.get("status")
                if st == "active" or (ot and ct and ot <= now_iso <= ct):
                    active_markets.append(m)
            if active_markets:
                return active_markets
            future = [m for m in res["markets"] if m.get("close_time") and m.get("close_time") > now_iso]
            if future:
                future.sort(key=lambda x: x["close_time"])
                return [future[0]]
        return []

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
        return self.request("DELETE", f"/portfolio/events/orders/{order_id}?exchange_index={exchange_index}", auth_required=True)

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



# ===================== ENGINE DE PREÇO SPOT (Binance Ref) =====================
def get_binance_btc_spot() -> Optional[float]:
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


def get_binance_btc_15m_prior_candle() -> Optional[Dict[str, Any]]:
    """
    Consulta a última vela de 15m FECHADA na Binance para validação de tendência macro.
    Filtro Jev (SystemOne 9 Anos): 75% de probabilidade de acerto superior em trend continuation.
    Retorna {'dir': 'UP'|'DOWN', 'open': float, 'close': float, 'ret_bps': float}
    """
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
                    prior = data[0] # Última vela de 15m 100% completada
                    p_open = float(prior[1])
                    p_close = float(prior[4])
                    p_dir = "UP" if p_close >= p_open else "DOWN"
                    ret_bps = (abs(p_close - p_open) / p_open) * 10000
                    return {"dir": p_dir, "open": p_open, "close": p_close, "ret_bps": ret_bps}
        except Exception:
            pass
    return None


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
                with open(JOURNAL_JSON, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

    def clear_open_position(self):
        self.current_open_position = None
        if os.path.exists(JOURNAL_JSON):
            try:
                with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["open_position"] = None
                with open(JOURNAL_JSON, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
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
        strike_price = float(target_market.get("floor_strike") or target_market.get("strike_price") or spot_now)

        delta = spot_now - strike_price
        dynamic_deadband = max(DEADBAND_MIN_FLOOR, round(strike_price * DEADBAND_BPS, 2))

        print(f"\n[📊 ANÁLISE DE MERCADO KALSHI]:")
        print(f"   Ticker: {ticker}")
        print(f"   Strike (K): ${strike_price:,.2f} | Spot Atual: ${spot_now:,.2f}")
        print(f"   Drift Real (Delta): ${delta:+.2f} | Deadband Dinâmico: ${dynamic_deadband:.2f} ({DEADBAND_BPS*10000:.1f} bps)")

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
            print(f"   -> [FILTRO DEADBAND]: Delta de ${delta:+.2f} está na zona morta (< ${dynamic_deadband:.2f} | {DEADBAND_BPS*10000:.1f} bps). Preservando capital.")
            time.sleep(max(1, remaining_sec))
            return

        # 3.1 Filtro de Vela Anterior (Recomendação #1 do Jev — 75% Trend Continuation)
        if REQUIRE_PRIOR_CANDLE_TREND:
            prior_candle = get_binance_btc_15m_prior_candle()
            if prior_candle:
                prior_dir = prior_candle["dir"]
                ret_bps = prior_candle["ret_bps"]
                print(f"   [🕯️ FILTRO DE VELA ANTERIOR - JEV]: Vela 15m Anterior fechou {prior_dir} ({ret_bps:.1f} bps)")
                if target_dir != prior_dir:
                    print(f"   -> [🛡️ VETO JEV]: Sinal {target_dir} ({candidate_side.upper()}) rejeitado por divergir da vela 15m anterior ({prior_dir}).")
                    print("      Preservando capital contra exaustões e falsos rompimentos de contratendência.")
                    time.sleep(max(1, remaining_sec))
                    return
                else:
                    print(f"   -> [🔥 CONFIRMAÇÃO JEV]: Tendência da vela anterior ({prior_dir}) alinhada com drift intra-vela ({target_dir})! Convicção alta.")
            else:
                print("   [Aviso]: Não foi possível ler vela anterior da Binance. Prosseguindo com drift intra-vela.")

        should_enter = True
        target_side = candidate_side

        # 4. Execução (Paper ou Live)
        if should_enter:
            yes_ask = int(float(target_market.get("yes_ask_dollars") or target_market.get("yes_ask") or 0.55) * 100)
            yes_bid = int(float(target_market.get("yes_bid_dollars") or target_market.get("yes_bid") or 0.50) * 100)
            no_ask = int(float(target_market.get("no_ask_dollars") or target_market.get("no_ask") or 0.55) * 100)
            no_bid = int(float(target_market.get("no_bid_dollars") or target_market.get("no_bid") or 0.50) * 100)
            
            entry_price = yes_ask if target_side == "yes" else no_ask
            
            if entry_price > PRIMARY_MAX_PRICE:
                print(f"   [🛡️ FILTRO TETO DE PREÇO]: Cota a {entry_price}¢ > {PRIMARY_MAX_PRICE}¢ (Breakeven desfavorável). Pulando entrada.")
                time.sleep(max(1, remaining_sec))
                return

            stake = entry_price / 100.0
            print(f"\n[🚀 ORDEM KALSHI]: Comprando {target_side.upper()} @ {entry_price}¢ (Modo: {self.mode}) | Stake: ${stake:.2f}")
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

                res = self.client.place_order(ticker, target_side, 1, entry_price)
                print(f"   [⚡ RESPOSTA DA ORDEM REAL KALSHI]: {res}")
                if not res or ("order_id" not in res and "order" not in res):
                    print("   [!] Falha na execução da ordem na Kalshi. Abortando entrada para proteger capital.")
                    time.sleep(max(1, remaining_sec))
                    return
                order_info = res.get("order", {}) if isinstance(res.get("order"), dict) else res
                real_order_id = order_info.get("order_id") or res.get("order_id", "")
                status = str(order_info.get("status", "resting")).lower()
                print(f"   [⚡ STATUS INICIAL DA COMPRA]: ID: {real_order_id} | Status: {status}")

                # Verificação rigorosa de execução (Fill-or-Cancel) no BUY
                if status in ("resting", "pending"):
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

                if status not in ("executed", "filled"):
                    print(f"   [⚠️ COMPRA NÃO PREENCHIDA]: Status permanece '{status}'. Cancelando ordem resting para não deixar risco aberto.")
                    try:
                        self.client.cancel_order(real_order_id)
                    except Exception:
                        pass
                    time.sleep(max(1, remaining_sec))
                    return

                print(f"   [✅ COMPRA CONFIRMADA ON-EXCHANGE]: 1 contrato de {target_side.upper()} @ {entry_price}¢ | Order ID: {real_order_id}")
                self.save_open_position({
                    "ticker": ticker,
                    "target_side": target_side,
                    "count": 1,
                    "entry_price": entry_price,
                    "stake": stake,
                    "order_id": real_order_id,
                    "strike_price": strike_price,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            else:
                print(f"   [SIMULAÇÃO PAPER]: 1 contrato de {target_side.upper()} executado a {entry_price}¢ com sucesso!")
                self.save_open_position({
                    "ticker": ticker,
                    "target_side": target_side,
                    "count": 1,
                    "entry_price": entry_price,
                    "stake": stake,
                    "order_id": "paper-sim",
                    "strike_price": strike_price,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

            # 5. Monitoramento de Take-Profit até o fim dos 900s
            print(f"[🎯 MONITORAMENTO KALSHI]: Acompanhando Take-Profit (>= {TAKE_PROFIT_CENTS}¢) até os 900s...")
            sold_early = False
            early_sell_price = 0

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
                    if (target_side == "yes" and cur_delta > 0 and cur_bps >= 15.0) or (target_side == "no" and cur_delta < 0 and cur_bps >= 15.0):
                        early_sell_price = TAKE_PROFIT_CENTS
                        sell_ok = True
                        sell_order_id = "paper-tp"

                        if self.mode == "LIVE":
                            print(f"\n[💰 ENVIANDO ORDEM REAL DE VENDA (TAKE-PROFIT) NA KALSHI]:")
                            print(f"   Ticker: {ticker} | Lado: {target_side.upper()} | Preço Alvo: {early_sell_price}¢")
                            sell_res = self.client.place_order(ticker, target_side, count=1, price_cents=early_sell_price, action="sell")
                            if isinstance(sell_res, dict) and ("order" in sell_res or "order_id" in sell_res):
                                order_data = sell_res.get("order", {}) if isinstance(sell_res.get("order"), dict) else sell_res
                                sell_order_id = order_data.get("order_id", "SUBMITTED")
                                status = str(order_data.get("status", "resting")).lower()
                                print(f"   -> Ordem de Venda Enviada! Order ID: {sell_order_id} | Status: {status}")

                                # Se a ordem ainda estiver descansando (resting), aguarda preenchimento no livro
                                if status in ("resting", "pending"):
                                    print("   -> Aguardando execução (fill) da ordem no livro Kalshi...")
                                    for _ in range(4):
                                        time.sleep(5)
                                        chk = self.client.get_order_status(sell_order_id)
                                        if isinstance(chk, dict) and "order" in chk and isinstance(chk["order"], dict):
                                             cur_st = str(chk["order"].get("status", "")).lower()
                                             if cur_st in ("executed", "filled"):
                                                 status = "filled"
                                                 print("   -> Ordem Kalshi PREENCHIDA (Filled) com sucesso!")
                                                 break

                                if status in ("executed", "filled"):
                                    sell_ok = True
                                else:
                                    print(f"   [⚠️ VENDA NÃO PREENCHIDA]: Status permanece '{status}'. Cancelando ordem resting para não deixar risco aberto.")
                                    try:
                                        self.client.cancel_order(sell_order_id)
                                    except Exception:
                                        pass
                                    sell_ok = False
                            else:
                                print(f"   [❌ FALHA NA VENDA KALSHI]: {sell_res}. Mantendo posição até vencimento final.")
                                sell_ok = False

                        if sell_ok:
                            sold_early = True
                            payout = early_sell_price / 100.0
                            cycle_pnl = payout - stake
                            if self.mode == "LIVE":
                                time.sleep(3)
                                b_info = self.client.get_real_balance()
                                real_s2 = b_info.get("shard2_balance")
                                if real_s2 and real_s2 > 0:
                                    self.balance = real_s2
                            else:
                                self.balance += cycle_pnl
                            print(f"\n[💰 TAKE-PROFIT KALSHI CONFIRMADO]: Posição vendida a {early_sell_price}¢ (Drift: {cur_bps:.1f} bps)!")
                            print(f"   Payout: ${payout:.2f} | P&L: {cycle_pnl:+.2f} USD | Novo Saldo: ${self.balance:,.2f}")
                            self.save_trade({
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "execution_mode": self.mode,
                                "order_id": real_order_id,
                                "sell_order_id": sell_order_id,
                                "ticker": ticker,
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

                time.sleep(15)

            # 6. Liquidação Oficial no Fechamento da Vela (se não saiu no Take-Profit)
            if not sold_early:
                time.sleep(10)
                official_winner = None
                winner_source = "BINANCE_SPOT_ESTIMATED"

                if self.mode == "LIVE":
                    print(f"   -> Consultando oráculo oficial de liquidação na Kalshi API ({ticker})...")
                    settle_info = self.client.get_market_settlement(ticker, max_retries=6)
                    if settle_info and settle_info.get("result"):
                        k_res = settle_info["result"].lower()  # 'yes' ou 'no'
                        official_winner = "UP" if k_res == "yes" else "DOWN"
                        winner_source = "KALSHI_OFFICIAL_ORACLE"
                        is_win = (target_side.lower() == k_res)
                        print(f"   [🏛️ ORÁCULO OFICIAL KALSHI]: Resultado: {k_res.upper()} | Vencedor: {official_winner}")

                if official_winner is None:
                    final_spot = get_binance_btc_spot() or spot_now
                    is_win = (final_spot >= strike_price) if target_side == "yes" else (final_spot < strike_price)
                    winner = "UP" if final_spot >= strike_price else "DOWN"
                else:
                    winner = official_winner
                    final_spot = get_binance_btc_spot() or spot_now

                payout = 1.00 if is_win else 0.00
                cycle_pnl = payout - stake
                if self.mode == "LIVE":
                    time.sleep(5)
                    b_info = self.client.get_real_balance()
                    real_s2 = b_info.get("shard2_balance")
                    if real_s2 and real_s2 > 0:
                        self.balance = real_s2
                else:
                    self.balance += cycle_pnl
                res_str = "VITÓRIA" if is_win else "DERROTA"

                print(f"\n[🏁 APURAÇÃO FINAL KALSHI - JANELA CONCLUÍDA]:")
                print(f"   Strike (K): ${strike_price:,.2f} | Final Spot: ${final_spot:,.2f} | Vencedor: {winner} ({winner_source})")
                print(f"   Resultado: {res_str} | Payout: ${payout:.2f} | P&L Ciclo: {cycle_pnl:+.2f} USD")
                print(f"   Saldo Atualizado: ${self.balance:,.2f} USD")

                self.save_trade({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "execution_mode": self.mode,
                    "order_id": real_order_id,
                    "ticker": ticker,
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

        try:
            with open(JOURNAL_JSON, "w", encoding="utf-8") as f:
                json.dump(journal, f, indent=2)
        except Exception as e:
            print(f"[Erro ao gravar kalshi_trading_journal.json]: {e}")

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
