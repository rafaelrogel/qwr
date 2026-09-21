import urllib.request
import json

queries = [
    "https://gamma-api.polymarket.com/events?search=bitcoin&active=true&closed=false",
    "https://gamma-api.polymarket.com/events?search=btc&active=true&closed=false",
    "https://gamma-api.polymarket.com/events?search=up&active=true&closed=false",
    "https://gamma-api.polymarket.com/markets?search=bitcoin&active=true&closed=false",
    "https://gamma-api.polymarket.com/markets?search=5m&active=true&closed=false"
]

for q in queries:
    req = urllib.request.Request(q, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
            print(f"URL: {q.split('?')[0]}?{q.split('?')[1]} -> {len(data)} resultados")
            for d in data[:5]:
                t = d.get("title") or d.get("question")
                print(f"  - {t} (slug: {d.get('slug')})")
    except Exception as e:
        print(f"Erro em {q}: {e}")
