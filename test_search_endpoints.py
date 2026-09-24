import json
import urllib.request
import urllib.parse

def test_endpoints():
    urls = [
        "https://gamma-api.polymarket.com/search?q=temperature",
        "https://gamma-api.polymarket.com/search?query=climate",
        "https://gamma-api.polymarket.com/public-search?q=oil",
        "https://gamma-api.polymarket.com/events?tag_slug=climate",
        "https://gamma-api.polymarket.com/events?tag_slug=science",
        "https://gamma-api.polymarket.com/events?tag_slug=weather",
        "https://gamma-api.polymarket.com/tags?limit=100"
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    for u in urls:
        print("Checking:", u)
        try:
            req = urllib.request.Request(u, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                if isinstance(data, list):
                    print("  List len:", len(data))
                    for item in data[:3]:
                        if isinstance(item, dict):
                            print("   -", item.get("label") or item.get("name") or item.get("title") or item.get("question") or item.get("slug"))
                elif isinstance(data, dict):
                    print("  Dict keys:", list(data.keys()))
                    for k in ["events", "markets", "tags"]:
                        if k in data and isinstance(data[k], list):
                            print(f"   {k} count: {len(data[k])}")
                            for item in data[k][:3]:
                                print(f"     [{k}]", item.get("title") or item.get("question") or item.get("label"))
        except Exception as e:
            print("  Error:", e)
        print("-" * 40)

if __name__ == "__main__":
    test_endpoints()
