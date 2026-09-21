import urllib.request
import json
import time
from datetime import datetime, timezone

now_ms = int(time.time() * 1000)
# Queremos de 16:50 até 19:16 de hoje (últimas ~2.5 a 3 horas)
start_ms = now_ms - (3 * 3600 * 1000)

url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&startTime={start_ms}&limit=1000"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req) as r:
    klines = json.loads(r.read().decode())

candles_1m = {}
for k in klines:
    ts_sec = int(k[0]) // 1000
    candles_1m[ts_sec] = {
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "volume": float(k[5]),
    }

# Filtrar ciclos de 5m
all_5m_ts = sorted([ts for ts in candles_1m.keys() if ts % 300 == 0])

print("CYCLE_TS | TIME_UTC | OPEN(Strike) | SPOT_135s | DELTA_135s | SPOT_255s | DELTA_255s | CLOSE | WINNER | PRIMARY_FILTER | SWEEPER_ELIGIBLE")
print("-" * 120)

for w_ts in all_5m_ts:
    dt = datetime.fromtimestamp(w_ts, tz=timezone.utc)
    # Apenas entre 15:40 UTC e agora (dependendo de fuso, vamos ver a hora local do usuario: 16:50 local pode ser 15:50 UTC ou 16:50 UTC)
    c0 = candles_1m.get(w_ts)
    c2 = candles_1m.get(w_ts + 120)
    c4 = candles_1m.get(w_ts + 240)
    
    if not (c0 and c2 and c4):
        continue

    strike = c0["open"]
    spot_135 = (c2["open"] + c2["close"]) / 2.0
    delta_135 = spot_135 - strike
    
    spot_255 = c4["open"]
    delta_255 = spot_255 - strike
    
    close = c4["close"]
    final_delta = close - strike
    winner = "UP" if close >= strike else "DOWN"

    # Deadband check (|delta| >= 15)
    primary_signal = None
    primary_reason = ""
    if abs(delta_135) < 15.0:
        primary_reason = f"Deadband (<$15): delta={delta_135:+.1f}"
    else:
        side = "UP" if delta_135 > 0 else "DOWN"
        primary_signal = side
        primary_reason = f"Gatilho {side} (delta={delta_135:+.1f})"

    # Sweeper check (|delta| >= 25)
    sweeper_signal = None
    if abs(delta_255) >= 25.0:
        sweeper_signal = "UP" if delta_255 > 0 else "DOWN"

    print(f"{w_ts} | {dt.strftime('%H:%M:%S')} | {strike:9.2f} | {spot_135:9.2f} | {delta_135:+10.2f} | {spot_255:9.2f} | {delta_255:+10.2f} | {close:9.2f} | {winner:5s} | {primary_reason:<25s} | Sweeper={sweeper_signal}")

