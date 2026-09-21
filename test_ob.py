from live_trader_5m import get_clob_orderbook, get_polymarket_market
import time

now_ts = int(time.time())
w_ts = (now_ts // 300) * 300
m = get_polymarket_market(w_ts)
if m:
    import json
    tokens = json.loads(m.get("clobTokenIds", "[]"))
    print(f"Window: {w_ts}")
    for idx, side in enumerate(["UP", "DOWN"]):
        ob = get_clob_orderbook(tokens[idx])
        print(f"Side {side}: {ob}")
else:
    print("Market not found")
