import urllib.request
import json

url = "https://gamma-api.polymarket.com/tags"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req, timeout=8) as resp:
        tags = json.loads(resp.read().decode())
        print(f"Total de tags: {len(tags)}")
        for t in tags[:25]:
            print(f" - {t.get('label')} (slug: {t.get('slug')})")
except Exception as e:
    print("Erro ao buscar tags:", e)
