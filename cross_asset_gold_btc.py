"""
Pesquisa Cross-Asset: Lead-Lag e Correlação de Spikes entre Ouro (XAU), S&P 500 (ES) e Bitcoin (BTC)
"""
import os
import csv
from datetime import datetime

poly_dir = r"C:\Users\rafae\.gemini\antigravity\scratch\polymarket-bot"

print("Testando Correlação e Lead-Lag Cross-Asset...")

# Vamos carregar uma amostra de timestamps alinhados de XAUUSD (Gold-Spot-XAUUSD-5-Minute-OHLC-Candles.csv) e BTC (BTCUSDT_5minutes.csv)
gold_path = os.path.join(poly_dir, "Gold-Spot-XAUUSD-5-Minute-OHLC-Candles.csv")
btc_path = os.path.join(poly_dir, "BTCUSDT_5minutes.csv")

# Mapeia retornos de 5m do Ouro por timestamp Unix
gold_returns = {}
with open(gold_path, "r", encoding="utf-8", errors="ignore") as f:
    reader = csv.DictReader(f)
    count = 0
    for r in reader:
        # ISO timestamp: 2026-04-29T09:55:00.000Z
        try:
            t_str = r["time"][:19]
            dt = datetime.strptime(t_str, "%Y-%m-%dT%H:%M:%S")
            ts = int(dt.timestamp())
            o = float(r["open"])
            c = float(r["close"])
            ret = (c - o) / o
            gold_returns[ts] = ret
            count += 1
            if count >= 300000: break
        except Exception:
            continue

print(f"Ouro 5m: {len(gold_returns):,} timestamps indexados.")

# Cruza com BTC
btc_same_dir = 0
btc_next_dir = 0
aligned_count = 0
strong_gold_move = 0
strong_gold_btc_aligned = 0
strong_gold_btc_next_aligned = 0

prev_gold_ret = None
with open(btc_path, "r", encoding="utf-8", errors="ignore") as f:
    reader = csv.DictReader(f)
    count = 0
    for r in reader:
        ts = int(r["timestamp"]) // 1000
        if ts in gold_returns:
            aligned_count += 1
            g_ret = gold_returns[ts]
            b_o = float(r["open"])
            b_c = float(r["close"])
            b_ret = (b_c - b_o) / b_o
            
            # Mesmo sentido na mesma vela
            if (g_ret > 0 and b_ret > 0) or (g_ret < 0 and b_ret < 0):
                btc_same_dir += 1
                
            # Se ouro teve movimento forte (> 0.08% em 5m)
            if abs(g_ret) > 0.0008:
                strong_gold_move += 1
                if (g_ret > 0 and b_ret > 0) or (g_ret < 0 and b_ret < 0):
                    strong_gold_btc_aligned += 1
                    
            if prev_gold_ret is not None and abs(prev_gold_ret) > 0.0008:
                if (prev_gold_ret > 0 and b_ret > 0) or (prev_gold_ret < 0 and b_ret < 0):
                    strong_gold_btc_next_aligned += 1
                    
            prev_gold_ret = g_ret
            
        count += 1
        if count >= 300000: break

print(f"Total de velas 5m alinhadas Ouro + BTC: {aligned_count:,}")
if aligned_count > 0:
    print(f"Alinhamento direcional natural (mesma vela): {btc_same_dir}/{aligned_count} = {(btc_same_dir/aligned_count*100):.2f}%")
if strong_gold_move > 0:
    print(f"Quando Ouro tem spike forte (>0.08% em 5m): BTC segue na mesma vela em {strong_gold_btc_aligned}/{strong_gold_move} = {(strong_gold_btc_aligned/strong_gold_move*100):.2f}%")
    print(f"Quando Ouro tem spike forte, BTC segue na PRÓXIMA vela (Lag +5m) em: {strong_gold_btc_next_aligned}/{strong_gold_move} = {(strong_gold_btc_next_aligned/strong_gold_move*100):.2f}%")
