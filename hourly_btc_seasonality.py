"""
Pesquisa de Sazonalidade Intradia: Probabilidade de UP e Volatilidade por Hora do Dia (UTC)
"""
import os
import csv
from datetime import datetime

poly_dir = r"C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot"
btc_path = os.path.join(poly_dir, "BTCUSDT_5minutes.csv")

hours_stats = {h: {"total": 0, "up": 0, "abs_ret_sum": 0.0} for h in range(24)}

with open(btc_path, "r", encoding="utf-8", errors="ignore") as f:
    reader = csv.DictReader(f)
    count = 0
    for r in reader:
        ts = int(r["timestamp"]) // 1000
        dt = datetime.utcfromtimestamp(ts)
        h = dt.hour
        
        o = float(r["open"])
        c = float(r["close"])
        is_up = c >= o
        abs_ret = abs(c - o) / o
        
        hours_stats[h]["total"] += 1
        if is_up:
            hours_stats[h]["up"] += 1
        hours_stats[h]["abs_ret_sum"] += abs_ret
        
        count += 1
        if count >= 300000: break

print("Hora (UTC) | Total Velas | % UP | Volatilidade Média 5m")
print("-" * 55)
for h in range(24):
    tot = hours_stats[h]["total"]
    pct_up = (hours_stats[h]["up"] / tot * 100) if tot else 0
    avg_vol = (hours_stats[h]["abs_ret_sum"] / tot * 100) if tot else 0
    print(f"  {h:02d}:00 UTC | {tot:,} velas | {pct_up:.2f}% UP | Vol: {avg_vol:.4f}%")
