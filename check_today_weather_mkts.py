import urllib.request
import json

tickers = ['KXHIGHAUS', 'KXHIGHMIA', 'KXHIGHCHI', 'KXHIGHTEWR', 'KXHIGHLAX', 'KXHIGHTDAL', 'KXHIGHTATL', 'KXHIGHTBOS', 'KXTEMPMIAH']
for t in tickers:
    url = f"https://external-api.kalshi.com/trade-api/v2/markets?series_ticker={t}&status=open"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            mkts = json.loads(r.read().decode()).get("markets", [])
            today_mkts = [m for m in mkts if "26SEP28" in m.get("ticker", "")]
            if today_mkts:
                print(f"\n=== {t} TODAY (26SEP28) - {len(today_mkts)} markets ===")
                for m in today_mkts:
                    print(f"  {m.get('ticker')}: {m.get('title')} | Yes Ask: {m.get('yes_ask_dollars')} | No Ask: {m.get('no_ask_dollars')}")
    except Exception as e:
        pass
