import json
import urllib.request
import time

def get_current_clob():
    now_ts = int(time.time())
    w_ts = (now_ts // 300) * 300
    slug = f"btc-updown-5m-{w_ts}"
    url = f"https://gamma-api.polymarket.com/events?slug={slug}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read().decode())
    m = data[0]["markets"][0]
    tokens = json.loads(m.get("clobTokenIds", "[]"))
    
    # Query CLOB orderbook for both tokens
    for idx, name in enumerate(["UP", "DOWN"]):
        t = tokens[idx]
        ob_url = f"https://clob.polymarket.com/book?token_id={t}"
        req_ob = urllib.request.Request(ob_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req_ob) as r:
            ob = json.loads(r.read().decode())
        asks = ob.get("asks", [])
        bids = ob.get("bids", [])
        best_bid = float(bids[0]["price"]) if bids else 0
        best_ask = float(asks[0]["price"]) if asks else 0
        print(f"Token {name}: Best Bid={best_bid} (size={bids[0]['size'] if bids else 0}), Best Ask={best_ask} (size={asks[0]['size'] if asks else 0})")
        print(f"  Total Asks: {len(asks)} | Asks: {asks[:3]}")

get_current_clob()
