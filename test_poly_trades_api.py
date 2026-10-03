import urllib.request
import json

url = "https://data-api.polymarket.com/trades?limit=25"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        trades = json.loads(resp.read().decode())
        print(f"Total live trades recebidos: {len(trades)}")
        for t in trades[:10]:
            title = t.get("title", "")
            outcome = t.get("outcome", "")
            side = t.get("side", "")
            size = float(t.get("size") or 0.0)
            price = float(t.get("price") or 0.0)
            usd_volume = round(size * price, 2)
            timestamp = t.get("timestamp")
            wallet = t.get("proxyWallet", "")
            print(f"[{side}] USD: ${usd_volume:>8.2f} | Price: ${price:.3f} | Size: {size:>7.1f} | Market: {title[:40]} | Wallet: {wallet[:8]}...")
except Exception as e:
    print(f"Erro trades API: {e}")
