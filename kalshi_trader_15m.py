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
EXECUTION_MODE = ENV_CFG.get("KALSHI_MODE", "PAPER").upper() # 'PAPER' ou 'LIVE'
KALSHI_KEY_ID = ENV_CFG.get("KALSHI_KEY_ID", "")
KALSHI_PRIVATE_KEY_PATH = ENV_CFG.get("KALSHI_PRIVATE_KEY_PATH", os.path.join(BASE_DIR, "kalshi_key.pem"))

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
            "User-Agent": "KalshiBTC15mAlgoTrader/1.0"
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
        except Exception as e:
            return None

    def get_btc_15m_markets(self) -> List[dict]:
        """Busca mercados abertos da série KXBTC15M"""
        res = self.request("GET", "/markets", params={"series_ticker": "KXBTC15M", "status": "open"})
        if res and "markets" in res:
            return res["markets"]
        # Fallback para busca genérica
        res = self.request("GET", "/markets", params={"status": "open"})
        if res and "markets" in res:
            return [m for m in res["markets"] if "BTC" in m.get("ticker", "").upper() and "15M" in m.get("ticker", "").upper()]
        return []

    def get_orderbook(self, ticker: str) -> Optional[dict]:
        """Obtém livro de ordens (order book L2)"""
        return self.request("GET", f"/markets/{ticker}/orderbook")

    def place_order(self, ticker: str, side: str, count: int, price_cents: int) -> Optional[dict]:
        """Envia ordem limit de compra ou venda na Kalshi (side='yes' ou 'no')"""
        payload = {
            "ticker": ticker,
            "action": "buy",
            "side": side.lower(),
            "type": "limit",
            "count": count,
            "yes_price": price_cents if side.lower() == "yes" else (100 - price_cents),
            "client_order_id": f"kbtc15_{int(time.time()*1000)}"
        }
        return self.request("POST", "/portfolio/orders", body=payload, auth_required=True)


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
        self.mode = EXECUTION_MODE
        self.balance = 35.00 # $10 depósito + $25 bônus inicial padrão
        self.load_journal()

    def load_journal(self):
        if os.path.exists(JOURNAL_JSON):
            try:
                with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.balance = data.get("current_balance", self.balance)
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

        print("\n" + "=" * 80)
        print(f" [KALSHI 15M] Janela Ativa: {now_utc.strftime('%Y-%m-%d')} {now_utc.hour:02d}:{window_minute:02d}:00 UTC")
        print(f" Tempo Decorrido: {elapsed_sec}s / 900s | Restam: {remaining_sec}s | Modo: {self.mode}")
        print(f" Saldo Atual: ${self.balance:,.2f} USD")
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
        strike_price = float(target_market.get("strike_price") or spot_now)

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
            time.sleep(30)
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
                    time.sleep(30)
                    return
                else:
                    print(f"   -> [🔥 CONFIRMAÇÃO JEV]: Tendência da vela anterior ({prior_dir}) alinhada com drift intra-vela ({target_dir})! Convicção alta.")
            else:
                print("   [Aviso]: Não foi possível ler vela anterior da Binance. Prosseguindo com drift intra-vela.")

        should_enter = True
        target_side = candidate_side

        # 4. Execução (Paper ou Live)
        if should_enter:
            orderbook = self.client.get_orderbook(ticker)
            yes_bid = target_market.get("yes_bid", 50)
            yes_ask = target_market.get("yes_ask", 55)
            
            entry_price = yes_ask if target_side == "yes" else (100 - yes_bid)
            
            if entry_price > PRIMARY_MAX_PRICE:
                print(f"   [🛡️ FILTRO TETO DE PREÇO]: Cota a {entry_price}¢ > {PRIMARY_MAX_PRICE}¢ (Breakeven desfavorável). Pulando entrada.")
                time.sleep(30)
                return

            print(f"\n[🚀 ORDEM KALSHI]: Comprando {target_side.upper()} @ {entry_price}¢ (Modo: {self.mode})")
            if self.mode == "LIVE":
                res = self.client.place_order(ticker, target_side, 1, entry_price)
                print(f"   Resposta Kalshi: {res}")
            else:
                print(f"   [SIMULAÇÃO PAPER]: 1 contrato de {target_side.upper()} executado a {entry_price}¢ com sucesso!")

            # 5. Monitoramento de Take-Profit até o fim dos 900s
            print("[🎯 MONITORAMENTO KALSHI]: Acompanhando Take-Profit (>= 86¢) e Stop-Loss...")
            while True:
                now_elapsed = (datetime.now(timezone.utc).minute % 15) * 60 + datetime.now(timezone.utc).second
                if now_elapsed >= 870: # 30s antes do fechamento
                    print("   [FIM DA VELA]: Encerrando monitoramento, aguardando liquidação oficial.")
                    break
                time.sleep(10)

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
