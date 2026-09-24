import json
import urllib.request
import urllib.parse

def test_search():
    # Let's test gamma api /markets endpoint with query and tags
    endpoints = [
        "https://gamma-api.polymarket.com/events?slug=climate",
        "https://gamma-api.polymarket.com/markets?limit=10&active=true&closed=false&query=temperature",
        "https://gamma-api.polymarket.com/markets?limit=10&active=true&closed=false&query=oil",
        "https://gamma-api.polymarket.com/markets?limit=10&active=true&closed=false&query=hurricane",
        "https://gamma-api.polymarket.com/markets?limit=10&active=true&closed=false&query=climate",
        "https://gamma-api.polymarket.com/markets?limit=10&active=true&closed=false&query=gas",
        "https://gamma-api.polymarket.com/tags"
    ]
    
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in endpoints:
        print(f"Testing URL: {url}")
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                if isinstance(data, list):
                    print(f"  Result count: {len(data)}")
                    if data:
                        first = data[0]
                        if isinstance(first, dict):
                            print(f"  First item: {first.get('question') or first.get('title') or first.get('label') or first.get('name')}")
                            if 'slug' in first:
                                print(f"  Slug: {first.get('slug')}")
                elif isinstance(data, dict):
                    print(f"  Dict keys: {list(data.keys())}")
        except Exception as e:
            print(f"  Error: {e}")
        print("-" * 50)

if __name__ == "__main__":
    test_search()
