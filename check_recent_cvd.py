import json
import urllib.request
import time

# Checar as velas de 22:05 (21:05 UTC)
url = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit=15"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req) as r:
    klines = json.loads(r.read().decode())

print("Minutos recentes da Binance Futures:")
for k in klines:
    ts = int(k[0]) // 1000
    dt_str = time.strftime('%H:%M:%S', time.gmtime(ts))
    o, h, l, c = float(k[1]), float(k[2]), float(k[3]), float(k[4])
    quote_vol = float(k[7])
    taker_buy = float(k[10])
    taker_sell = quote_vol - taker_buy
    vd = taker_buy - taker_sell
    print(f"{dt_str} UTC | Open: {o} | Close: {c} | Vol: ${quote_vol/1e6:.2f}M | CVD: ${vd/1e6:+.2f}M")
