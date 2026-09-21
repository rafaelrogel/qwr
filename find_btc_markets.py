import urllib.request
import json

def find_btc_markets():
    # Busca eventos ou mercados relacionados a Bitcoin
    urls = [
        "https://gamma-api.polymarket.com/events?limit=50&active=true&closed=false",
        "https://gamma-api.polymarket.com/markets?limit=100&active=true&closed=false"
    ]
    
    found = []
    for u in urls:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                items = json.loads(resp.read().decode("utf-8"))
                for item in items:
                    title = item.get("title") or item.get("question") or ""
                    slug = item.get("slug") or ""
                    desc = item.get("description") or ""
                    text = f"{title} {slug} {desc}".lower()
                    if "bitcoin" in text or "btc" in text:
                        found.append({
                            "type": "event" if "events" in u else "market",
                            "title": title,
                            "slug": slug,
                            "endDate": item.get("endDate"),
                            "volume": item.get("volume") or item.get("volume24hr")
                        })
        except Exception as e:
            print(f"Erro em {u}: {e}")

    print(f"Total encontrados: {len(found)}")
    # Exibir os 15 mais relevantes com 5m, 15m, up, down ou maior volume
    for f in found[:25]:
        print(f"[{f['type']}] {f['title']}")
        print(f"  Slug: {f['slug']} | End: {f['endDate']} | Vol: {f['volume']}\n")

if __name__ == "__main__":
    find_btc_markets()
