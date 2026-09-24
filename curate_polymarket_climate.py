import json
import sys
import urllib.request
import urllib.parse

# Set UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

def search_query(q):
    url = f"https://gamma-api.polymarket.com/public-search?q={urllib.parse.quote(q)}"
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("events", [])
    except Exception as e:
        print(f"Error {q}: {e}")
        return []

def search_tag(tag):
    url = f"https://gamma-api.polymarket.com/events?tag_slug={urllib.parse.quote(tag)}&closed=false&limit=100"
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            if isinstance(data, list):
                return data
            return []
    except Exception as e:
        print(f"Error tag {tag}: {e}")
        return []

def get_market_details(market_id):
    url = f"https://gamma-api.polymarket.com/markets/{market_id}"
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except:
        return {}

def main():
    queries = [
        "temperature", "climate", "weather", "hottest", "warmest",
        "hurricane", "storm", "oil", "crude", "wti", "brent", 
        "natural gas", "gasoline", "eia", "noaa", "cpc"
    ]
    tags = ["climate", "weather", "science", "energy"]
    
    all_events = {}
    
    for q in queries:
        for ev in search_query(q):
            all_events[ev.get("id")] = ev

    for t in tags:
        for ev in search_tag(t):
            all_events[ev.get("id")] = ev

    # Filter to only relevant keywords in title or questions
    domain_keywords = [
        "temperature", "climate", "hottest", "warmest", "weather", 
        "hurricane", "storm", "earthquake", "oil", "crude", "wti", 
        "brent", "gas", "gasoline", "energy", "co2", "noaa", "eia"
    ]
    
    curated = []
    for eid, ev in all_events.items():
        title = ev.get("title", "")
        desc = ev.get("description", "")
        text = (title + " " + desc).lower()
        if not any(k in text for k in domain_keywords):
            continue
            
        closed = ev.get("closed", False)
        markets = ev.get("markets", [])
        active_submarkets = [m for m in markets if not m.get("closed", False)]
        
        curated.append({
            "id": eid,
            "title": title,
            "slug": ev.get("slug"),
            "closed": closed,
            "active_count": len(active_submarkets),
            "volume": float(ev.get("volume", 0) or 0),
            "volume24hr": float(ev.get("volume24hr", 0) or 0),
            "markets": markets,
            "active_submarkets": active_submarkets
        })
        
    curated.sort(key=lambda x: x["volume"], reverse=True)
    
    with open("polymarket_climate_energy_analysis.json", "w", encoding="utf-8") as f:
        json.dump(curated, f, indent=2, ensure_ascii=False)
        
    print(f"=== Total Curated Events: {len(curated)} ===\n")
    
    # Split into Active vs Closed
    active = [e for e in curated if not e["closed"] and e["active_count"] > 0]
    print(f"--- ACTIVE / OPEN MARKETS ({len(active)}) ---")
    for ev in active:
        print(f"\n★ {ev['title']}")
        print(f"  URL: https://polymarket.com/event/{ev['slug']}")
        print(f"  Volume Total: ${ev['volume']:,.2f} | 24h: ${ev['volume24hr']:,.2f}")
        for m in ev["active_submarkets"]:
            q = m.get("question")
            outcomes = m.get("outcomes")
            prices = m.get("outcomePrices")
            end = m.get("endDate")
            print(f"    • {q}")
            print(f"      Odds: {outcomes} -> {prices} (End: {end})")
            
    print(f"\n--- HISTORICAL / PREVIOUS MARKETS (Sample) ---")
    closed = [e for e in curated if e["closed"] or e["active_count"] == 0]
    for ev in closed[:12]:
        print(f"  - {ev['title']} (Vol: ${ev['volume']:,.2f}) -> {ev['slug']}")

if __name__ == "__main__":
    main()
