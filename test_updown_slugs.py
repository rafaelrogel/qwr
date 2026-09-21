import urllib.request
import json
import time

now = int(time.time())
print(f"Timestamp atual: {now}")

# Testa buscar eventos com slug contendo btc-updown
queries = [
    "https://gamma-api.polymarket.com/events?limit=50&active=true&closed=false",
    "https://gamma-api.polymarket.com/markets?limit=100&active=true&closed=false"
]

for q in queries:
    req = urllib.request.Request(q, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            for item in data:
                slug = item.get("slug", "")
                if "updown" in slug or "5m" in slug or "btc" in slug:
                    print(f"Match em {q.split('?')[0]}: {slug} | Title: {item.get('title') or item.get('question')}")
    except Exception as e:
        print(f"Erro em {q}: {e}")
