import urllib.request
import json

url = "https://gamma-api.polymarket.com/markets?limit=1&active=true&closed=false"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read().decode())
    m = data[0]
    print("Chaves disponíveis no mercado:")
    for k in sorted(m.keys()):
        print(f" - {k}: {repr(m[k])[:80]}")
