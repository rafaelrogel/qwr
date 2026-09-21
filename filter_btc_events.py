import urllib.request
import json

url = "https://gamma-api.polymarket.com/events?limit=200&active=true&closed=false"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req, timeout=12) as resp:
        events = json.loads(resp.read().decode())
        print(f"Total de eventos lidos: {len(events)}")
        btc_events = []
        for e in events:
            title = e.get("title", "")
            slug = e.get("slug", "")
            text = f"{title} {slug}".lower()
            if any(k in text for k in ["btc", "bitcoin", "5m", "15m", "up or down", "up/down"]):
                btc_events.append(e)

        print(f"Encontrados {len(btc_events)} eventos com BTC/Bitcoin/Up/Down:")
        for b in btc_events:
            print(f"- {b.get('title')} (slug: {b.get('slug')})")
            markets = b.get("markets", [])
            for m in markets:
                print(f"   ↳ Mercado: {m.get('question')} | Precos: {m.get('outcomePrices')} | Vol: ${float(m.get('volume', 0)):,.2f}")
except Exception as e:
    print("Erro:", e)
