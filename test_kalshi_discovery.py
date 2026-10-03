from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import requests

def test_market_discovery(simulated_utc=None):
    now_utc = simulated_utc or datetime.now(timezone.utc)
    now_ts = int(now_utc.timestamp())
    now_iso = now_utc.isoformat()
    ny_tz = ZoneInfo("America/New_York")
    now_et = now_utc.astimezone(ny_tz)
    
    if now_et.hour in (3, 4):
        return f"KALSHI_HALT: Maintenance window ({now_et.strftime('%H:%M')} ET / {now_utc.strftime('%H:%M')} UTC)"
    
    # Check L1 Time-Bounded Query
    params = {"series_ticker": "KXBTC15M", "min_close_ts": now_ts, "max_close_ts": now_ts + 1200, "limit": 10}
    r = requests.get("https://api.elections.kalshi.com/trade-api/v2/markets", params=params)
    markets = r.json().get("markets", [])
    if markets:
        return f"L1_MATCH: {markets[0].get('ticker')}"
    
    # Check L2 Deterministic Ticker Lookup
    rem_min = 15 - (now_et.minute % 15)
    close_et = (now_et + timedelta(minutes=rem_min)).replace(second=0, microsecond=0)
    ticker = f"KXBTC15M-{close_et.strftime('%y%b%d%H%M').upper()}-{close_et.strftime('%M')}"
    r2 = requests.get(f"https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}")
    if r2.status_code == 200:
        return f"L2_DETERMINISTIC_MATCH: {r2.json().get('market', {}).get('ticker')}"
    return "NO_MARKET_FOUND"

now = datetime.now(timezone.utc)
print("Current time (08:17 UTC):", test_market_discovery(now))

future = datetime(2026, 10, 1, 9, 5, 0, tzinfo=timezone.utc)
print("Simulated 09:05 UTC (05:05 ET):", test_market_discovery(future))

future2 = datetime(2026, 10, 1, 9, 20, 0, tzinfo=timezone.utc)
print("Simulated 09:20 UTC (05:20 ET):", test_market_discovery(future2))
