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
        self.is_running = False
        self.thread = None
        self.last_tick_time = 0.0
        self.connected = False
        self.total_buy_usd = 0.0
        self.total_sell_usd = 0.0

    def start(self):
        """Inicia a thread em segundo plano se ainda não estiver ativa"""
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="BinanceCVDWatcher")
        self.thread.start()
        print("[BinanceCVDWatcher] Thread de monitoramento de CVD (btcusdt@aggTrade) iniciada.")

    def stop(self):
        self.is_running = False

    def _run_loop(self):
        """Loop async para manter conexao persistente com reconexao automatica"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._websocket_listener())

    async def _websocket_listener(self):
        url = "wss://stream.binance.com:9443/ws/btcusdt@aggTrade"
        while self.is_running:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=15, open_timeout=10) as ws:
                    self.connected = True
                    while self.is_running:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=20)
                            data = json.loads(msg)
                            # m = true significa que o comprador foi maker (logo o vendedor foi taker)
                            # m = false significa que o comprador foi taker (agressão de compra)
                            is_buyer_maker = data.get("m", False)
                            p = float(data.get("p", 0.0))
                            q = float(data.get("q", 0.0))
                            vol_usd = p * q
                            now = time.time()
                            self.last_tick_time = now

                            is_taker_buy = not is_buyer_maker
                            if is_taker_buy:
                                self.total_buy_usd += vol_usd
                            else:
                                self.total_sell_usd += vol_usd

                            self.trades.append((now, is_taker_buy, vol_usd))

                        except asyncio.TimeoutError:
                            continue
            except Exception:
                self.connected = False
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
        for t_time, is_buy, vol in reversed(trades_copy):
            if t_time < cutoff:
                break
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
                "source": "WEBSOCKET_TICKS",
                "connected": self.connected and not is_stale
            }

        # Fallback REST: calcular CVD a partir das klines de 1m mais recentes da Binance Futures
        return self._get_rest_fallback_cvd(window_seconds)

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
