import sys
import json
import urllib.request
import time
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')

# 1. Carregar histórico detalhado das últimas 5 horas (17:20 até agora)
now_ms = int(datetime.now().timestamp() * 1000)
start_ms = now_ms - (5 * 3600 * 1000)

url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&startTime={start_ms}&limit=1000"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req) as r:
    klines = json.loads(r.read().decode())

candles = {}
for k in klines:
    ts = int(k[0]) // 1000
    candles[ts] = {
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "vol": float(k[5])
    }

from forensic_1720_to_2141 import windows_to_check

def get_token_price(delta_usd: float, elapsed_sec: int) -> float:
    time_factor = 1.0 + (elapsed_sec / 300.0) * 1.8
    prob = 0.50 + (delta_usd / (220.0 / time_factor))
    return max(0.02, min(0.99, prob))

# Configurações de Sweeper para simular:
# 1. Atual Conservador: 255s, Delta >= 25, Preço <= 0.965
# 2. Agressivo Moderado: 240s (Minuto 4:00), Delta >= 20, Preço <= 0.975
# 3. Ultra Agressivo: 230s (Minuto 3:50), Delta >= 18, Preço <= 0.985

configs = [
    {"name": "Atual (Ultraconservador)", "eval_sec": 255, "min_delta": 25.0, "max_price": 0.965, "min_price": 0.55},
    {"name": "Agressivo Moderado (240s / $0.975)", "eval_sec": 240, "min_delta": 20.0, "max_price": 0.975, "min_price": 0.50},
    {"name": "Ultra Agressivo (230s / $0.985)", "eval_sec": 230, "min_delta": 18.0, "max_price": 0.985, "min_price": 0.50},
]

sim_results = {c["name"]: {"trades": 0, "wins": 0, "losses": 0, "stake": 0.0, "payout": 0.0, "pnl": 0.0, "reversals": []} for c in configs}

for tw in windows_to_check:
    th, tm, _ = map(int, tw.split(":"))
    utc_h = th - 1
    
    matched_ts = None
    for ts in candles.keys():
        if ts % 300 == 0:
            dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
            if dt_utc.hour == utc_h and dt_utc.minute == tm:
                matched_ts = ts
                break

    if not matched_ts:
        continue

    c0 = candles.get(matched_ts)
    c3 = candles.get(matched_ts + 180) # min 3
    c4 = candles.get(matched_ts + 240) # min 4
    if not (c0 and c3 and c4):
        continue

    strike = c0["open"]
    close = c4["close"]
    winner = "UP" if close >= strike else "DOWN"

    for cfg in configs:
        c_name = cfg["name"]
        eval_sec = cfg["eval_sec"]
        min_delta = cfg["min_delta"]
        max_p = cfg["max_price"]
        min_p = cfg["min_price"]

        # Estimar spot no momento de avaliacao
        if eval_sec >= 240:
            # minuto 4
            eval_spot = c4["open"]
        else:
            # minuto 3.8
            eval_spot = (c3["close"] + c4["open"]) / 2.0

        delta_eval = eval_spot - strike
        
        if abs(delta_eval) >= min_delta:
            target_side = "UP" if delta_eval > 0 else "DOWN"
            p_up = get_token_price(delta_eval, eval_sec)
            price = p_up if target_side == "UP" else (1.0 - p_up)
            
            if min_p <= price <= max_p:
                stake = 1.00
                shares = stake / price
                sim_results[c_name]["trades"] += 1
                sim_results[c_name]["stake"] += stake
                
                if target_side == winner:
                    payout = round(shares * 1.00, 2)
                    pnl = payout - stake
                    sim_results[c_name]["wins"] += 1
                    sim_results[c_name]["payout"] += payout
                    sim_results[c_name]["pnl"] += pnl
                else:
                    payout = 0.00
                    pnl = -stake
                    sim_results[c_name]["losses"] += 1
                    sim_results[c_name]["payout"] += payout
                    sim_results[c_name]["pnl"] += pnl
                    sim_results[c_name]["reversals"].append({
                        "window": tw,
                        "strike": strike,
                        "eval_spot": eval_spot,
                        "delta_eval": delta_eval,
                        "target_side": target_side,
                        "final_close": close,
                        "winner": winner,
                        "price": price,
                        "loss": -1.00
                    })

print("=" * 105)
print(f"SIMULAÇÃO COMPARATIVA NO PERÍODO DAS 17h20 ÀS 21h40 (53 VELAS DE HOJE)")
print("=" * 105)
print(f"{'CONFIGURAÇÃO DO SWEEPER':<32} | {'TRADES':<7} | {'V/D':<9} | {'WIN RATE':<9} | {'STAKE':<9} | {'PAYOUT':<9} | {'LUCRO LÍQUIDO':<13} | {'ROI'}")
print("-" * 105)

for cfg in configs:
    c_name = cfg["name"]
    res = sim_results[c_name]
    wr = (res["wins"] / res["trades"] * 100) if res["trades"] > 0 else 0.0
    roi = (res["pnl"] / res["stake"] * 100) if res["stake"] > 0 else 0.0
    print(f"{c_name:<32} | {res['trades']:<7} | {res['wins']}V / {res['losses']}D | {wr:6.1f}%  | ${res['stake']:6.2f} | ${res['payout']:6.2f} | {res['pnl']:+8.2f} USDC | {roi:+5.1f}%")

print("-" * 105)
for cfg in configs:
    c_name = cfg["name"]
    revs = sim_results[c_name]["reversals"]
    print(f"\n[!] Reversões / Derrotas sofridas por '{c_name}': {len(revs)}")
    for r in revs:
        print(f"    * Janela {r['window']}: Entrou em {r['target_side']} a ${r['price']:.2f} (Delta: {r['delta_eval']:+.1f}), mas vela fechou em {r['winner']} ({r['final_close'] - r['strike']:+.1f}) -> Perda de -$1.00 USDC!")

