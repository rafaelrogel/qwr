import urllib.request
import json

tickers = [
    'KXHIGHAUS', 'HIGHAUS', 'KXHIGHMIA', 'HIGHMIA', 
    'KXHIGHCHI', 'KXHIGHOU', 'HIGHNY', 'KXHIGHTEWR', 
    'KXHIGHLAX', 'KXHIGHTDAL', 'KXHIGHTATL', 'KXHIGHTBOS',
    'KXTEMPAUSH', 'KXTEMPMIAH', 'KXTEMPCHIH', 'KXTEMPNYCH'
]
found = {}
for t in tickers:
    url = f"https://external-api.kalshi.com/trade-api/v2/markets?series_ticker={t}&status=open"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            mkts = json.loads(r.read().decode()).get("markets", [])
            if mkts:
                found[t] = mkts
    except Exception as e:
        pass

print(f"Series with open markets: {list(found.keys())}")
for t, mlist in found.items():
    print(f"\n=== {t} ({len(mlist)} open markets) ===")
    for m in mlist[:5]:
        print(f"  {m.get('ticker')}: {m.get('title')} | Yes Ask: {m.get('yes_ask_dollars')} | No Ask: {m.get('no_ask_dollars')} | Closes: {m.get('close_time')}")
