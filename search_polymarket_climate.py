import json
import urllib.request
import urllib.parse

def search_polymarket(query):
    url = f"https://gamma-api.polymarket.com/events?closed=false&limit=20&order=volume24hr&ascending=false&title={urllib.parse.quote(query)}"
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data
    except Exception as e:
        print(f"Error querying {query}: {e}")
        return []

def search_public_markets():
    keywords = [
        "temperature", "warmest", "hottest", "climate", "weather", 
        "hurricane", "oil", "crude", "gas", "energy", "co2", "natural gas"
    ]
    
    seen_ids = set()
    found = []
    
    for kw in keywords:
        results = search_polymarket(kw)
        for ev in results:
            ev_id = ev.get("id")
            if ev_id in seen_ids:
                continue
            seen_ids.add(ev_id)
            
            title = ev.get("title", "")
            desc = ev.get("description", "")
            vol = float(ev.get("volume", 0) or 0)
            vol24 = float(ev.get("volume24hr", 0) or 0)
            markets = ev.get("markets", [])
            
            found.append({
                "id": ev_id,
                "title": title,
                "volume": vol,
                "volume24hr": vol24,
                "slug": ev.get("slug"),
                "category": ev.get("category", ""),
                "markets_count": len(markets),
                "sample_market": markets[0] if markets else None
            })
            
    # Sort by volume
    found.sort(key=lambda x: x["volume"], reverse=True)
    return found

if __name__ == "__main__":
    results = search_public_markets()
    print(f"Total events found: {len(results)}\n")
    for r in results[:25]:
        sample = r.get("sample_market") or {}
        q = sample.get("question", "")
        outcomes = sample.get("outcomes", "")
        prices = sample.get("outcomePrices", "")
        print(f"=== {r['title']} ===")
        print(f"  Volume Total: ${r['volume']:,.2f} | 24h: ${r['volume24hr']:,.2f} | Category: {r['category']}")
        print(f"  Slug: https://polymarket.com/event/{r['slug']}")
        if q:
            print(f"  Question: {q}")
            print(f"  Outcomes: {outcomes} | Prices: {prices}")
        print()
