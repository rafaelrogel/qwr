"""
=============================================================================
BINANCE CVD WATCHER (REAL-TIME CUMULATIVE VOLUME DELTA TICK STREAM)
=============================================================================
Monitora continuamente em tempo real os negócios agressivos a mercado (Ticks)
no contrato perpétuo de Bitcoin (BTCUSDT Futures) via WebSocket (btcusdt@aggTrade).

Mecânica do CVD (Cumulative Volume Delta):
- Se m == False: Comprador foi o agressor a mercado (Taker Buy) -> Delta Positivo (+)
- Se m == True: Vendedor foi o agressor a mercado (Taker Sell) -> Delta Negativo (-)
- Volume em Dólar = Preço * Quantidade

Fornece:
- net_cvd_usd: Saldo líquido de agressão em USD na janela
- cvd_ratio: Proporção de agressão compradora vs vendedora
- dominant_signal: 'UP', 'DOWN' ou 'NEUTRAL'
- Fallback REST automático para klines de 1m se a conexão oscilar
=============================================================================
"""

import threading
import time
import json
import collections
import urllib.request
from typing import Dict, Any, Optional

try:
    import websockets
    import asyncio
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False


class BinanceCVDWatcher:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BinanceCVDWatcher, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        # Guarda os últimos 30.000 ticks (~5 a 10 minutos de negócios rápidos)
        self.trades = collections.deque(maxlen=30000)
        self.altcoin_trades = collections.defaultdict(lambda: collections.deque(maxlen=10000))
        self.is_running = False
        self.thread = None
        self.last_tick_time = 0.0
        self.connected = False
        self.total_buy_usd = 0.0
        self.total_sell_usd = 0.0
        self.stream_type = "FUTURES"
        self.last_book_ticker = {
            "bid_p": 0.0, "bid_q": 0.0, "ask_p": 0.0, "ask_q": 0.0,
            "mid_p": 0.0, "spread": 0.0, "obi": 0.0, "microprice": 0.0,
            "time": 0.0
        }
        self.book_ticker_history = collections.deque(maxlen=3000)

    def start(self):
        """Inicia a thread em segundo plano se ainda não estiver ativa"""
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="BinanceCVDWatcher")
        self.thread.start()
        print(f"[BinanceCVDWatcher] Thread de monitoramento multi-stream Binance Futures/Spot iniciada.")

    def stop(self):
        self.is_running = False

    def _run_loop(self):
        """Loop async para manter conexao persistente com reconexao automatica"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._websocket_listener())

    async def _websocket_listener(self):
        urls = [
            "wss://fstream.binancefuture.com/stream?streams=btcusdt@aggTrade/ethusdt@aggTrade/solusdt@aggTrade/dogeusdt@aggTrade/btcusdt@bookTicker",
            "wss://stream.binance.com:9443/stream?streams=btcusdt@aggTrade/ethusdt@aggTrade/solusdt@aggTrade/dogeusdt@aggTrade/btcusdt@bookTicker"
        ]
        url_idx = 0
        while self.is_running:
            url = urls[url_idx % len(urls)]
            is_futures = "fstream" in url
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=15, open_timeout=10) as ws:
                    self.connected = True
                    self.stream_type = "FUTURES" if is_futures else "SPOT"
                    while self.is_running:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=20)
                            raw = json.loads(msg)
                            stream = raw.get("stream", "")
                            data = raw.get("data", raw)
                            now = time.time()
                            self.last_tick_time = now

                            # 1. Tratamento de BookTicker (Top of Book / OBI / Microprice)
                            if "bookticker" in stream.lower() or ("b" in data and "a" in data and "B" in data and "A" in data):
                                bid_p = float(data.get("b", 0.0))
                                bid_q = float(data.get("B", 0.0))
                                ask_p = float(data.get("a", 0.0))
                                ask_q = float(data.get("A", 0.0))
                                tot_q = bid_q + ask_q
                                if tot_q > 0:
                                    obi = (bid_q - ask_q) / tot_q
                                    mid_p = (bid_p + ask_p) / 2.0
                                    micro_p = (bid_p * ask_q + ask_p * bid_q) / tot_q
                                    spread = ask_p - bid_p
                                    self.last_book_ticker = {
                                        "bid_p": bid_p,
                                        "bid_q": bid_q,
                                        "ask_p": ask_p,
                                        "ask_q": ask_q,
                                        "mid_p": round(mid_p, 2),
                                        "spread": round(spread, 2),
                                        "obi": round(obi, 4),
                                        "microprice": round(micro_p, 2),
                                        "time": now
                                    }
                                    self.book_ticker_history.append((now, obi, mid_p, micro_p, spread))
                                continue

                            # 2. Tratamento de AggTrade (Ticks / Agressao)
                            is_buyer_maker = data.get("m", False)
                            p = float(data.get("p", 0.0))
                            q = float(data.get("q", 0.0))
                            vol_usd = p * q

                            is_taker_buy = not is_buyer_maker
                            sym = data.get("s", "BTCUSDT").upper()

                            if "btcusdt" in stream or sym == "BTCUSDT":
                                if is_taker_buy:
                                    self.total_buy_usd += vol_usd
                                else:
                                    self.total_sell_usd += vol_usd
                                self.trades.append((now, is_taker_buy, vol_usd, q, p))
                            else:
                                self.altcoin_trades[sym].append((now, is_taker_buy, vol_usd, q, p))

                        except asyncio.TimeoutError:
                            continue
            except Exception:
                self.connected = False
                url_idx += 1
                await asyncio.sleep(2.5)

    def get_window_cvd(self, window_seconds: int = 135) -> Dict[str, Any]:
        """
        Retorna o Cumulative Volume Delta (CVD) nos últimos `window_seconds`.
        Se o WebSocket tiver menos de 10 ticks, faz fallback rápido na API REST da Binance Futures.
        """
        cutoff = time.time() - window_seconds
        buy_usd = 0.0
        sell_usd = 0.0
        tick_count = 0

        # Snapshot thread-safe dos ticks
        trades_copy = list(self.trades)
        for trade in reversed(trades_copy):
            t_time = trade[0]
            if t_time < cutoff:
                break
            is_buy = trade[1]
            vol = trade[2]
            tick_count += 1
            if is_buy:
                buy_usd += vol
            else:
                sell_usd += vol

        # Se temos dados suficientes de ticks em tempo real
        now = time.time()
        is_stale = (now - self.last_tick_time) > 30.0 if self.last_tick_time > 0 else True

        if is_stale and self.last_tick_time > 0:
            # Audit 2.12: Websocket parou de receber ticks por >30s - forca NEUTRAL
            return {
                "taker_buy_usd": round(buy_usd, 2),
                "taker_sell_usd": round(sell_usd, 2),
                "net_cvd_usd": 0.0,
                "cvd_ratio": 0.50,
                "dominant_signal": "NEUTRAL",
                "ticks": tick_count,
                "source": "STALE_TICKS_NEUTRAL",
                "connected": False
            }

        if tick_count >= 50 and not is_stale:
            net_cvd = buy_usd - sell_usd
            total_vol = buy_usd + sell_usd
            ratio = (buy_usd / total_vol) if total_vol > 0 else 0.50

            dominant = "NEUTRAL"
            if abs(net_cvd) >= 150_000: # Mínimo $150k de dominância líquida
                if ratio >= 0.52 and net_cvd > 0:
                    dominant = "UP"
                elif ratio <= 0.48 and net_cvd < 0:
                    dominant = "DOWN"

            return {
                "taker_buy_usd": round(buy_usd, 2),
                "taker_sell_usd": round(sell_usd, 2),
                "net_cvd_usd": round(net_cvd, 2),
                "cvd_ratio": round(ratio, 4),
                "dominant_signal": dominant,
                "ticks": tick_count,
                "source": f"{getattr(self, 'stream_type', 'FUTURES')}_WEBSOCKET_TICKS",
                "connected": self.connected and not is_stale
            }

        # Fallback REST: calcular CVD a partir das klines de 1m mais recentes da Binance Futures
        return self._get_rest_fallback_cvd(window_seconds)

    def get_microstructure_spike(
        self,
        lookback_sec: float = 4.0,
        min_spike_usd: float = 200_000.0,
        whale_threshold_btc: float = 3.5
    ) -> Dict[str, Any]:
        """
        Detector de Agressão Atípica e Disparos de Microestrutura (Desk 10 Alpha):
        Mede a aceleração de volume agressor (CVD Spike) e presença de ordens de baleias
        nos últimos `lookback_sec` segundos.
        """
        now = time.time()
        cutoff = now - lookback_sec
        buy_usd = 0.0
        sell_usd = 0.0
        whale_buys = 0
        whale_sells = 0
        tick_count = 0

        trades_copy = list(self.trades)
        for trade in reversed(trades_copy):
            t_time = trade[0]
            if t_time < cutoff:
                break
            is_buy = trade[1]
            vol = trade[2]
            q = trade[3] if len(trade) > 3 else 0.0
            tick_count += 1

            if is_buy:
                buy_usd += vol
                if q >= whale_threshold_btc:
                    whale_buys += 1
            else:
                sell_usd += vol
                if q >= whale_threshold_btc:
                    whale_sells += 1

        net_spike_usd = buy_usd - sell_usd
        total_spike_usd = buy_usd + sell_usd
        ratio = (buy_usd / total_spike_usd) if total_spike_usd > 0 else 0.50

        spike_detected = False
        direction = "NEUTRAL"
        confidence = 0.50

        # Condição de Disparo de Agressão Violenta
        if abs(net_spike_usd) >= min_spike_usd:
            if ratio >= 0.72 and net_spike_usd > 0:
                spike_detected = True
                direction = "UP"
                confidence = min(0.95, 0.75 + (ratio - 0.72) * 0.5 + (0.05 if whale_buys > 0 else 0.0))
            elif ratio <= 0.28 and net_spike_usd < 0:
                spike_detected = True
                direction = "DOWN"
                confidence = min(0.95, 0.75 + (0.28 - ratio) * 0.5 + (0.05 if whale_sells > 0 else 0.0))
        elif (whale_buys > 0 or whale_sells > 0) and total_spike_usd >= 100_000.0:
            if whale_buys > whale_sells and ratio >= 0.65:
                spike_detected = True
                direction = "UP"
                confidence = 0.82
            elif whale_sells > whale_buys and ratio <= 0.35:
                spike_detected = True
                direction = "DOWN"
                confidence = 0.82

        # Confirmação Cross-Asset com Altcoins (DOGE e SOL)
        alt_alignment = self.get_altcoin_breadth_alignment(lookback_sec=15.0)
        alt_aligned_count = 0
        alt_opposed_count = 0
        for s_name, s_data in alt_alignment.items():
            if s_data.get("direction") == direction and direction != "NEUTRAL":
                alt_aligned_count += 1
            elif s_data.get("direction") != "NEUTRAL" and s_data.get("direction") != direction:
                alt_opposed_count += 1

        if spike_detected:
            if alt_aligned_count >= 1:
                confidence = min(0.98, confidence + 0.05)
            elif alt_opposed_count >= 1:
                confidence = max(0.60, confidence - 0.10)

        # 4. Verificação de BookTicker Imbalance (OBI) & Anti-Absorção / Squeeze Harvester (Valentino Model)
        obi_data = self.get_order_book_imbalance(lookback_sec=3.0)
        rolling_obi = obi_data.get("rolling_obi", 0.0)
        absorption_warning = False
        squeeze_opportunity = False
        squeeze_direction = "NEUTRAL"
        squeeze_confidence = 0.0
        trapped_volume_usd = 0.0
        trapped_side = "NONE"

        if spike_detected:
            if direction == "UP":
                if rolling_obi <= -0.35:
                    # Armadilha de Absorção Institucional (Compradores agredindo contra parede densa de venda)
                    absorption_warning = True
                    confidence = max(0.40, confidence - 0.25)
                    spike_detected = False  # Veto preventivo no breakout naive (74.2% de falha)

                    # ALPHA OFENSIVO: Squeeze por Absorção (Fabio Valentino Model)
                    # Compradores viram combustível involuntário (trapped longs). Ao falhar no topo, gera squeeze de venda.
                    squeeze_opportunity = True
                    squeeze_direction = "DOWN"
                    squeeze_confidence = min(0.89, 0.76 + abs(rolling_obi) * 0.15 + (0.04 if whale_buys >= 1 else 0.0))
                    trapped_volume_usd = buy_usd
                    trapped_side = "LONGS"
                elif rolling_obi >= 0.35:
                    confidence = min(0.99, confidence + 0.06)
            elif direction == "DOWN":
                if rolling_obi >= 0.35:
                    # Armadilha de Absorção (Vendedores agredindo contra piso espesso de compra)
                    absorption_warning = True
                    confidence = max(0.40, confidence - 0.25)
                    spike_detected = False  # Veto preventivo no breakdown naive

                    # ALPHA OFENSIVO: Squeeze por Absorção (Fabio Valentino Model)
                    # Vendedores viram combustível involuntário (trapped shorts). Ao segurar no suporte, gera squeeze de compra.
                    squeeze_opportunity = True
                    squeeze_direction = "UP"
                    squeeze_confidence = min(0.89, 0.76 + abs(rolling_obi) * 0.15 + (0.04 if whale_sells >= 1 else 0.0))
                    trapped_volume_usd = sell_usd
                    trapped_side = "SHORTS"
                elif rolling_obi <= -0.35:
                    confidence = min(0.99, confidence + 0.06)

        # Detecção adicional quando agressão pesada ocorre diretamente contra a parede do book (|OBI| >= 0.40)
        if not squeeze_opportunity:
            if buy_usd >= 140_000 and ratio >= 0.68 and rolling_obi <= -0.40:
                absorption_warning = True
                squeeze_opportunity = True
                squeeze_direction = "DOWN"
                squeeze_confidence = min(0.87, 0.74 + abs(rolling_obi) * 0.15 + (0.04 if whale_buys >= 1 else 0.0))
                trapped_volume_usd = buy_usd
                trapped_side = "LONGS"
            elif sell_usd >= 140_000 and ratio <= 0.32 and rolling_obi >= 0.40:
                absorption_warning = True
                squeeze_opportunity = True
                squeeze_direction = "UP"
                squeeze_confidence = min(0.87, 0.74 + abs(rolling_obi) * 0.15 + (0.04 if whale_sells >= 1 else 0.0))
                trapped_volume_usd = sell_usd
                trapped_side = "SHORTS"

        # Ajuste de confiança por alinhamento de altcoins no Squeeze
        if squeeze_opportunity:
            if alt_opposed_count == 0 and alt_aligned_count >= 1:
                squeeze_confidence = min(0.95, squeeze_confidence + 0.03)
            elif alt_opposed_count >= 2:
                squeeze_confidence = max(0.60, squeeze_confidence - 0.08)

        return {
            "spike_detected": spike_detected,
            "direction": direction,
            "confidence": round(confidence, 3),
            "net_spike_usd": round(net_spike_usd, 2),
            "total_spike_usd": round(total_spike_usd, 2),
            "spike_ratio": round(ratio, 4),
            "whale_buys": whale_buys,
            "whale_sells": whale_sells,
            "alt_aligned": alt_aligned_count,
            "alt_opposed": alt_opposed_count,
            "altcoin_breadth": alt_alignment,
            "stream_type": getattr(self, "stream_type", "FUTURES"),
            "bookticker_obi": rolling_obi,
            "absorption_warning": absorption_warning,
            "squeeze_opportunity": squeeze_opportunity,
            "squeeze_direction": squeeze_direction,
            "squeeze_confidence": round(squeeze_confidence, 3),
            "trapped_volume_usd": round(trapped_volume_usd, 2),
            "trapped_side": trapped_side,
            "obi_data": obi_data,
            "ticks": tick_count,
            "lookback_sec": lookback_sec
        }

    def get_order_book_imbalance(self, lookback_sec: float = 3.0) -> Dict[str, Any]:
        """
        Retorna o Order Book Imbalance (OBI) e Microprice dos ultimos `lookback_sec`.
        OBI = (Q_bid - Q_ask) / (Q_bid + Q_ask)
        Range: [-1.0, +1.0]
        """
        now = time.time()
        cutoff = now - lookback_sec
        obis = []
        last = getattr(self, "last_book_ticker", {})

        for item in reversed(list(getattr(self, "book_ticker_history", []))):
            t = item[0]
            if t < cutoff:
                break
            obis.append(item[1])

        rolling_obi = round(sum(obis) / max(1, len(obis)), 4) if obis else last.get("obi", 0.0)
        latest_obi = last.get("obi", 0.0)
        mid_p = last.get("mid_p", 0.0)
        micro_p = last.get("microprice", 0.0)
        spread = last.get("spread", 0.0)

        obi_direction = "NEUTRAL"
        if rolling_obi >= 0.35:
            obi_direction = "UP"
        elif rolling_obi <= -0.35:
            obi_direction = "DOWN"

        return {
            "latest_obi": latest_obi,
            "rolling_obi": rolling_obi,
            "obi_direction": obi_direction,
            "bid_qty": last.get("bid_q", 0.0),
            "ask_qty": last.get("ask_q", 0.0),
            "spread_usd": spread,
            "mid_price": mid_p,
            "microprice": micro_p,
            "microprice_divergence": round(micro_p - mid_p, 2) if mid_p > 0 else 0.0,
            "samples": len(obis),
            "is_fresh": (now - last.get("time", 0)) <= 5.0 if last.get("time", 0) > 0 else False
        }

    def get_altcoin_breadth_alignment(self, lookback_sec: float = 15.0) -> Dict[str, Any]:
        """
        Calcula o fluxo líquido (CVD) e ratio de altcoins de alto beta (SOL, DOGE)
        nos últimos `lookback_sec` para confirmação cross-asset.
        """
        cutoff = time.time() - lookback_sec
        res = {}
        for sym, d_queue in list(self.altcoin_trades.items()):
            b_usd = 0.0
            s_usd = 0.0
            for item in reversed(d_queue):
                t = item[0]
                if t < cutoff:
                    break
                is_buy = item[1]
                vol = item[2]
                if is_buy:
                    b_usd += vol
                else:
                    s_usd += vol
            net = b_usd - s_usd
            tot = b_usd + s_usd
            ratio = (b_usd / tot) if tot > 0 else 0.5
            dir_sig = "UP" if (ratio >= 0.55 and net > 10_000) else ("DOWN" if (ratio <= 0.45 and net < -10_000) else "NEUTRAL")
            res[sym] = {
                "net_usd": round(net, 2),
                "ratio": round(ratio, 4),
                "direction": dir_sig
            }
        return res

    def _get_rest_fallback_cvd(self, window_seconds: int) -> Dict[str, Any]:
        """Fallback via REST klines caso o websocket esteja inicializando"""
        try:
            url = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit=5"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3.0) as r:
                klines = json.loads(r.read().decode())

            now_sec = time.time()
            cutoff = now_sec - window_seconds

            buy_usd = 0.0
            sell_usd = 0.0

            for k in klines:
                k_start = int(k[0]) // 1000
                k_end = int(k[6]) // 1000
                if k_end >= cutoff:
                    tot_q = float(k[7])
                    buy_q = float(k[10])
                    sell_q = tot_q - buy_q
                    buy_usd += buy_q
                    sell_usd += sell_q

            net_cvd = buy_usd - sell_usd
            total_vol = buy_usd + sell_usd
            ratio = (buy_usd / total_vol) if total_vol > 0 else 0.50

            dominant = "NEUTRAL"
            if abs(net_cvd) >= 150_000:
                if ratio >= 0.52 and net_cvd > 0:
                    dominant = "UP"
                elif ratio <= 0.48 and net_cvd < 0:
                    dominant = "DOWN"

            return {
                "taker_buy_usd": round(buy_usd, 2),
                "taker_sell_usd": round(sell_usd, 2),
                "net_cvd_usd": round(net_cvd, 2),
                "cvd_ratio": round(ratio, 4),
                "dominant_signal": dominant,
                "ticks": 0,
                "source": "REST_KLINES_FALLBACK",
                "connected": self.connected
            }
        except Exception:
            return {
                "taker_buy_usd": 0.0,
                "taker_sell_usd": 0.0,
                "net_cvd_usd": 0.0,
                "cvd_ratio": 0.50,
                "dominant_signal": "NEUTRAL",
                "ticks": 0,
                "source": "UNAVAILABLE",
                "connected": False
            }


# Instância global singleton
_global_cvd_watcher: Optional[BinanceCVDWatcher] = None

def get_cvd_watcher() -> BinanceCVDWatcher:
    global _global_cvd_watcher
    if _global_cvd_watcher is None:
        _global_cvd_watcher = BinanceCVDWatcher()
        _global_cvd_watcher.start()
    return _global_cvd_watcher


if __name__ == "__main__":
    print("Testando BinanceCVDWatcher ao vivo...")
    watcher = get_cvd_watcher()
    for i in range(8):
        time.sleep(1.0)
        stats = watcher.get_window_cvd(135)
        print(f"[{i+1}s] Source: {stats['source']} | Ticks: {stats['ticks']} | Net CVD: ${stats['net_cvd_usd']/1e6:+.2f}M | Ratio: {stats['cvd_ratio']*100:.1f}% | Sinal: {stats['dominant_signal']}")
