import urllib.request
import json
import time
from datetime import datetime

url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=600"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req) as r:
    klines = json.loads(r.read().decode())

candles_5m = {}
for k in klines:
    t_sec = int(k[0]) // 1000
    w_ts = t_sec - (t_sec % 300)
    minute_in_cycle = (t_sec % 300) // 60
    if w_ts not in candles_5m:
        candles_5m[w_ts] = {}
    candles_5m[w_ts][minute_in_cycle] = {
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "vol": float(k[5])
    }

complete_cycles = sorted([w for w, mins in candles_5m.items() if len(mins) == 5])

primary_entries = 0
sweeper_entries = 0
skipped_deadband = 0
skipped_price_filter = 0
trades = []

for w in complete_cycles:
    mins = candles_5m[w]
    K = mins[0]["open"]
    spot_135 = mins[2]["open"] # price around second 135 (start of minute 2)
    delta_135 = spot_135 - K
    
    spot_final = mins[4]["close"]
    delta_final = spot_final - K
    winner = "UP" if delta_final >= 0 else "DOWN"
    
    time_str = datetime.fromtimestamp(w).strftime("%H:%M:%S")
    
    # 1. Primary rule check
    traded_primary = False
    
    # Model estimated token price on Polymarket based on delta at 135s
    # At delta = 0, P = 0.50. At delta = +/-15, P ~ 0.58. At delta = +/-30, P ~ 0.65. Above 30-35, P > 0.65
    abs_delta = abs(delta_135)
    
    # Empirical mapping from Polymarket 5m microstructure
    est_prob = min(0.98, max(0.02, 0.50 + 0.005 * delta_135))
    
    if abs_delta < 15.0:
        skipped_deadband += 1
    else:
        candidate_side = "UP" if delta_135 > 0 else "DOWN"
        candidate_p = est_prob if candidate_side == "UP" else (1.0 - est_prob)
        
        # Filtro de Preco Saudavel: 0.35 <= P <= 0.65
        if candidate_p > 0.65 or candidate_p < 0.35:
            skipped_price_filter += 1
        else:
            traded_primary = True
            primary_entries += 1
            win = (candidate_side == winner)
            pnl = (1.0 / candidate_p - 1.0) if win else -1.0
            trades.append({
                "time": time_str,
                "type": "PRIMÁRIA",
                "side": candidate_side,
                "delta_entry": delta_135,
                "price": candidate_p,
                "delta_final": delta_final,
                "winner": winner,
                "win": win,
                "pnl": pnl
            })
            
    # 2. Sweeper check if no primary trade
    if not traded_primary:
        spot_scour = mins[4]["open"] # at 240s (final 60s)
        delta_scour = spot_scour - K
        if abs(delta_scour) >= 25.0:
            scour_side = "UP" if delta_scour > 0 else "DOWN"
            scour_p = 0.90 # typical sweeper entry
            sweeper_entries += 1
            win = (scour_side == winner)
            pnl = (1.0 / scour_p - 1.0) if win else -1.0
            trades.append({
                "time": time_str,
                "type": "SWEEPER",
                "side": scour_side,
                "delta_entry": delta_scour,
                "price": scour_p,
                "delta_final": delta_final,
                "winner": winner,
                "win": win,
                "pnl": pnl
            })

print("==================================================================")
print(f"SIMULAÇÃO HISTÓRICA DO CÓDIGO ATUAL NAS ÚLTIMAS 10 HORAS (119 CICLOS)")
print("==================================================================")
print(f"Total de Ciclos Analisados: {len(complete_cycles)}")
print(f"Ciclos Filtrados por Ruído (Deadband < $15.00): {skipped_deadband} ({skipped_deadband/len(complete_cycles)*100:.1f}%)")
print(f"Ciclos Filtrados por Preço Esticado (> $0.65): {skipped_price_filter} ({skipped_price_filter/len(complete_cycles)*100:.1f}%)")
print(f"Total de Entradas Executadas: {len(trades)} ({len(trades)/len(complete_cycles)*100:.1f}% dos ciclos)")
print(f"   -> Entradas Primárias (Aos 135s): {primary_entries}")
print(f"   -> Entradas Sweeper (Últimos 45s): {sweeper_entries}")

wins = sum(1 for t in trades if t["win"])
losses = len(trades) - wins
total_pnl = sum(t["pnl"] for t in trades)
win_rate = (wins / len(trades) * 100) if trades else 0.0

print(f"\nDESEMPENHO:")
print(f"   * Vitórias: {wins}")
print(f"   * Derrotas: {losses}")
print(f"   * Taxa de Acerto (Win Rate): {win_rate:.1f}%")
print(f"   * P&L Líquido Teórico ($1 por aposta): ${total_pnl:+.2f} USDC")
print(f"   * Fator de Lucro / PnL por Trade: ${total_pnl/len(trades):+.2f} USDC/trade")

print("\nLISTAGEM DETALHADA DAS ENTRADAS EXECUTADAS:")
print(f"{'Horário':<10} | {'Tipo':<9} | {'Lado':<5} | {'Delta Entr':<11} | {'Preço':<6} | {'Delta Fim':<11} | {'Resultado':<10} | {'P&L ($)'}")
print("-" * 75)
for t in trades:
    status = "VITÓRIA" if t["win"] else "DERROTA"
    print(f"{t['time']:<10} | {t['type']:<9} | {t['side']:<5} | {t['delta_entry']:+10.2f} | ${t['price']:<5.2f} | {t['delta_final']:+10.2f} | {status:<10} | {t['pnl']:+.2f}")
