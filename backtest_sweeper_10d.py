import sys
import json
import urllib.request
import time

sys.stdout.reconfigure(encoding='utf-8')

# Carregar 10 dias de velas da Binance
now_ms = int(time.time() * 1000)
ten_days_ms = now_ms - (10 * 24 * 3600 * 1000)
start_ms = (ten_days_ms // 300000) * 300000

all_1m = []
curr_start = start_ms

while curr_start < now_ms:
    url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&startTime={curr_start}&limit=1000"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            klines = json.loads(r.read().decode())
            if not klines:
                break
            all_1m.extend(klines)
            curr_start = klines[-1][0] + 60000
            time.sleep(0.05)
    except:
        break

candles_1m = {}
for k in all_1m:
    ts_sec = int(k[0]) // 1000
    candles_1m[ts_sec] = {
        "open": float(k[1]),
        "close": float(k[4]),
    }

all_5m_ts = sorted([ts for ts in candles_1m.keys() if ts % 300 == 0])

def get_token_price(delta_usd: float, elapsed_sec: int) -> float:
    time_factor = 1.0 + (elapsed_sec / 300.0) * 1.8
    prob = 0.50 + (delta_usd / (220.0 / time_factor))
    return max(0.02, min(0.99, prob))

configs = [
    {"name": "Atual (255s / $0.965 / Delta $25)", "eval_sec": 255, "min_delta": 25.0, "max_price": 0.965, "min_price": 0.55},
    {"name": "Agressivo Moderado (240s / $0.975 / Delta $20)", "eval_sec": 240, "min_delta": 20.0, "max_price": 0.975, "min_price": 0.50},
    {"name": "Ultra Agressivo (230s / $0.985 / Delta $18)", "eval_sec": 230, "min_delta": 18.0, "max_price": 0.985, "min_price": 0.50},
]

res = {c["name"]: {"trades": 0, "wins": 0, "losses": 0, "stake": 0.0, "payout": 0.0, "pnl": 0.0} for c in configs}

for w_ts in all_5m_ts:
    c0 = candles_1m.get(w_ts)
    c3 = candles_1m.get(w_ts + 180)
    c4 = candles_1m.get(w_ts + 240)
    if not (c0 and c3 and c4):
        continue

    strike = c0["open"]
    close = c4["close"]
    winner = "UP" if close >= strike else "DOWN"

    for cfg in configs:
        c_name = cfg["name"]
        eval_sec = cfg["eval_sec"]
        min_d = cfg["min_delta"]
        max_p = cfg["max_price"]
        min_p = cfg["min_price"]

        eval_spot = c4["open"] if eval_sec >= 240 else (c3["close"] + c4["open"]) / 2.0
        delta = eval_spot - strike

        if abs(delta) >= min_d:
            side = "UP" if delta > 0 else "DOWN"
            p_up = get_token_price(delta, eval_sec)
            price = p_up if side == "UP" else (1.0 - p_up)

            if min_p <= price <= max_p:
                stake = 1.00
                shares = stake / price
                res[c_name]["trades"] += 1
                res[c_name]["stake"] += stake

                if side == winner:
                    payout = round(shares * 1.00, 2)
                    res[c_name]["wins"] += 1
                    res[c_name]["payout"] += payout
                    res[c_name]["pnl"] += (payout - stake)
                else:
                    res[c_name]["losses"] += 1
                    res[c_name]["pnl"] -= stake

print("\n" + "=" * 105)
print("TESTE HISTÓRICO DE 10 DIAS DO SWEEPER (2.880 VELAS DE 5 MINUTOS)")
print("=" * 105)
print(f"{'CONFIGURAÇÃO':<42} | {'TRADES':<7} | {'V/D':<12} | {'WIN RATE':<9} | {'VOLUME':<10} | {'LUCRO LÍQUIDO':<14} | {'ROI'}")
print("-" * 105)

for cfg in configs:
    c_name = cfg["name"]
    r = res[c_name]
    wr = (r["wins"] / r["trades"] * 100) if r["trades"] > 0 else 0.0
    roi = (r["pnl"] / r["stake"] * 100) if r["stake"] > 0 else 0.0
    print(f"{c_name:<42} | {r['trades']:<7} | {r['wins']}V / {r['losses']}D  | {wr:6.1f}%  | ${r['stake']:8.2f} | {r['pnl']:+9.2f} USDC | {roi:+5.1f}%")

print("=" * 105 + "\n")
