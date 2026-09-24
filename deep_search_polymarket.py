import json
import urllib.request
import urllib.parse

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
    url = f"https://gamma-api.polymarket.com/events?tag_slug={urllib.parse.quote(tag)}&closed=false&limit=50"
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

def main():
    queries = [
        "temperature", "climate", "weather", "hottest", "warmest",
        "hurricane", "oil", "crude", "natural gas", "gasoline", "energy"
    ]
    tags = ["climate", "weather", "science"]
    
    all_events = {}
    
    for q in queries:
        events = search_query(q)
        for ev in events:
            eid = ev.get("id")
            if eid not in all_events:
                all_events[eid] = ev

    for t in tags:
        events = search_tag(t)
        for ev in events:
            eid = ev.get("id")
            if eid not in all_events:
                all_events[eid] = ev

    print(f"Total unique events found: {len(all_events)}\n")
    
    # Filter active/unclosed markets
    active_events = []
    closed_events = []
    
    for eid, ev in all_events.items():
        title = ev.get("title", "")
        slug = ev.get("slug", "")
        closed = ev.get("closed", False)
        vol = float(ev.get("volume", 0) or 0)
        vol24 = float(ev.get("volume24hr", 0) or 0)
        markets = ev.get("markets", [])
        
        # Check if any market is active
        has_active_market = any(not m.get("closed", False) for m in markets)
        
        info = {
            "id": eid,
            "title": title,
            "slug": slug,
            "closed": closed,
            "has_active_market": has_active_market,
            "volume": vol,
            "volume24hr": vol24,
            "markets": markets
        }
        
        if not closed and has_active_market:
            active_events.append(info)
        else:
            closed_events.append(info)
            
    active_events.sort(key=lambda x: x["volume"], reverse=True)
    closed_events.sort(key=lambda x: x["volume"], reverse=True)
    
    print(f"--- ACTIVE MARKETS ({len(active_events)}) ---")
    for ev in active_events:
        print(f"Title: {ev['title']}")
        print(f"  URL: https://polymarket.com/event/{ev['slug']}")
        print(f"  Volume: ${ev['volume']:,.2f} (24h: ${ev['volume24hr']:,.2f})")
        for m in ev["markets"]:
            if not m.get("closed", False):
                q = m.get("question", "")
                outcomes = m.get("outcomes", "")
                prices = m.get("outcomePrices", "")
                end_date = m.get("endDate", "")
                print(f"    - Submarket: {q}")
                print(f"      Outcomes: {outcomes} | Prices: {prices} | End: {end_date}")
        print()

    print(f"\n--- RECENT / CLOSED HISTORICAL MARKETS SAMPLE ({len(closed_events)}) ---")
    for ev in closed_events[:10]:
        print(f"Title: {ev['title']} | Vol: ${ev['volume']:,.2f} | Slug: {ev['slug']}")

if __name__ == "__main__":
    main()
