import urllib.request
import json

url = "https://gamma-api.polymarket.com/events?limit=50&active=true&closed=false&tag=weather"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        events = json.loads(resp.read().decode())
        print(f"Total Polymarket weather events: {len(events)}")
        for e in events:
            title = e.get("title", "")
            slug = e.get("slug", "")
            mkts = e.get("markets", [])
            print(f"\n[EVENT] {title} (Slug: {slug}) - {len(mkts)} markets")
            for m in mkts[:3]:
                q = m.get("question", "")
                prices = m.get("outcomePrices", "")
                end = m.get("endDate", "")
                print(f"   -> Q: {q} | Prices: {prices} | End: {end}")
except Exception as e:
    print(f"Poly error: {e}")
