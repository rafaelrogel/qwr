import time
from binance_cvd_watcher import get_cvd_watcher

w = get_cvd_watcher()
time.sleep(4)
print(f"Connected: {w.connected} | Trades count: {len(w.trades)}")
for i in range(5):
    time.sleep(1)
    stats = w.get_window_cvd(60)
    print(f"[{i+1}s] Source: {stats['source']} | Ticks: {stats['ticks']} | CVD: ${stats['net_cvd_usd']/1e6:+.2f}M | Ratio: {stats['cvd_ratio']*100:.1f}%")
