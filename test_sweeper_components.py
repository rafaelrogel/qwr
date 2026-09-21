import time
from live_trader_5m import get_clob_orderbook, get_binance_spot, get_chainlink_price, get_polymarket_market

now_ts = int(time.time())
w_ts = (now_ts // 300) * 300
elapsed = now_ts - w_ts
print(f"Elapsed: {elapsed}s")

m = get_polymarket_market(w_ts)
if m:
    import json
    tokens = json.loads(m.get("clobTokenIds", "[]"))
    token_up, token_down = tokens[0], tokens[1]
    
    cl = get_chainlink_price()
    b_spot = get_binance_spot()
    print(f"Chainlink: {cl} | Binance: {b_spot}")
    
    for side, tok in [("UP", token_up), ("DOWN", token_down)]:
        t0 = time.time()
        ob = get_clob_orderbook(tok)
        dt = time.time() - t0
        print(f"Orderbook {side} (took {dt:.2f}s): {ob}")
