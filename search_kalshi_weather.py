import urllib.request
import json

# Try series lookup
url_series = "https://external-api.kalshi.com/trade-api/v2/series"
req = urllib.request.Request(url_series, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        all_series = data.get("series", [])
        weather_series = [
            s for s in all_series 
            if any(k in s.get("ticker", "").lower() for k in ["high", "temp", "rain", "snow", "weather", "metar"])
            or any(k in s.get("title", "").lower() for k in ["temperature", "weather", "degrees", "precipitation"])
        ]
        print(f"Total series found matching weather/temperature: {len(weather_series)}")
        for s in weather_series:
            print(f"Ticker: {s.get('ticker')} | Title: {s.get('title')} | Frequency: {s.get('frequency')}")
            # check open markets for this series
            m_url = f"https://external-api.kalshi.com/trade-api/v2/markets?series_ticker={s.get('ticker')}&status=open"
            req_m = urllib.request.Request(m_url, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(req_m, timeout=5) as resp_m:
                    m_data = json.loads(resp_m.read().decode())
                    mkts = m_data.get("markets", [])
                    print(f"   -> Open markets: {len(mkts)}")
                    for m in mkts[:2]:
                        print(f"      {m.get('ticker')}: {m.get('title')} | YES: {m.get('yes_ask_dollars')} | NO: {m.get('no_ask_dollars')}")
            except Exception as em:
                print(f"      Err: {em}")
except Exception as e:
    print(f"Series lookup err: {e}")
