"""
=============================================================================
BINANCE LIQUIDATION WATCHER (REAL-TIME ORDER FLOW / CASCADE DETECTOR)
=============================================================================
Monitora continuamente em segundo plano o fluxo de liquidações forçadas de
Bitcoin (BTCUSDT) no mercado futuro da Binance via WebSocket (!forceOrder@arr).

Mecânica:
- Long Liquidado (Side SELL): Corretora despeja venda a mercado -> Pressão DOWN
- Short Liquidado (Side BUY): Corretora compra a mercado -> Pressão UP
=============================================================================
"""

import threading
import time
import json
import collections
from typing import Dict, Any, Optional

try:
    import websockets
    import asyncio
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False


class BinanceLiquidationWatcher:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(BinanceLiquidationWatcher, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.events = collections.deque(maxlen=300) # Guarda últimos eventos
        self.is_running = False
        self.thread = None
        self.last_event_time = 0.0
        self.connected = False
        self.total_long_usd = 0.0
        self.total_short_usd = 0.0

    def start(self):
        """Inicia a thread em segundo plano se ainda não estiver ativa"""
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="BinanceLiqWatcher")
        self.thread.start()
        print("[BinanceLiqWatcher] Thread de monitoramento de liquidacoes iniciada.")

    def stop(self):
        self.is_running = False

    def _run_loop(self):
        """Loop async para manter conexao persistente com reconexao automatica"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._websocket_listener())

    async def _websocket_listener(self):
        url = "wss://fstream.binance.com/ws/!forceOrder@arr"
        while self.is_running:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=15) as ws:
                    self.connected = True
                    while self.is_running:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=25)
                            data = json.loads(msg)
                            o = data.get("o", {})
                            sym = o.get("s")
                            # Filtra apenas Bitcoin
                            if sym == "BTCUSDT":
                                side = o.get("S") # SELL = Long liquidado | BUY = Short liquidado
                                qty = float(o.get("q", 0))
                                price = float(o.get("p", 0))
                                vol_usd = qty * price
                                now = time.time()
                                self.last_event_time = now

                                if side == "SELL":
                                    self.total_long_usd += vol_usd
                                elif side == "BUY":
                                    self.total_short_usd += vol_usd

                                self.events.append({
                                    "time": now,
                                    "side": side,
                                    "qty": qty,
                                    "price": price,
                                    "vol_usd": vol_usd
                                })
                        except asyncio.TimeoutError:
                            # Apenas timeout de leitura sem dados, continua conectado
                            continue
            except Exception as e:
                self.connected = False
                await asyncio.sleep(3.0)

    def get_window_liquidations(self, window_seconds: int = 150) -> Dict[str, Any]:
        """
        Retorna as liquidações ocorridas nos últimos `window_seconds` segundos.
        - long_vol_usd: Volume em USD de compradores liquidados (pressão de QUEDA)
        - short_vol_usd: Volume em USD de vendedores liquidados (pressão de ALTA)
        - dominant_signal: 'DOWN', 'UP' ou 'NEUTRAL'
        """
        cutoff = time.time() - window_seconds
        long_vol = 0.0
        short_vol = 0.0
        count = 0

        # Snapshot thread-safe
        events_copy = list(self.events)
        for ev in events_copy:
            if ev["time"] >= cutoff:
                count += 1
                if ev["side"] == "SELL":
                    long_vol += ev["vol_usd"]
                elif ev["side"] == "BUY":
                    short_vol += ev["vol_usd"]

        total_vol = long_vol + short_vol
        imbalance = 0.0
        if total_vol > 0:
            imbalance = (short_vol - long_vol) / total_vol

        dominant = "NEUTRAL"
        # Convicção: se volume relevante (>= $30k) e forte assimetria (> 65% para um lado)
        if total_vol >= 30_000:
            if imbalance <= -0.30:
                dominant = "DOWN"
            elif imbalance >= 0.30:
                dominant = "UP"

        return {
            "long_vol_usd": round(long_vol, 2),
            "short_vol_usd": round(short_vol, 2),
            "total_vol_usd": round(total_vol, 2),
            "imbalance": round(imbalance, 2),
            "count": count,
            "dominant_signal": dominant,
            "connected": self.connected
        }


# Instância global singleton
_global_watcher: Optional[BinanceLiquidationWatcher] = None

def get_liquidation_watcher() -> BinanceLiquidationWatcher:
    global _global_watcher
    if _global_watcher is None:
        _global_watcher = BinanceLiquidationWatcher()
        _global_watcher.start()
    return _global_watcher


if __name__ == "__main__":
    print("Testando BinanceLiquidationWatcher...")
    watcher = get_liquidation_watcher()
    for i in range(10):
        time.sleep(1.0)
        stats = watcher.get_window_liquidations(60)
        print(f"[{i+1}s] Connected: {stats['connected']} | Longs: ${stats['long_vol_usd']:,.0f} | Shorts: ${stats['short_vol_usd']:,.0f} | Signal: {stats['dominant_signal']}")
