import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("polymarket_climate_energy_analysis.json", "r", encoding="utf-8") as f:
    events = json.load(f)

print("=== UPCOMING WEATHER / TEMPERATURE MARKETS ===")
upcoming_weather = []
for ev in events:
    if ev.get("closed"):
        continue
    title = ev.get("title", "")
    if "temperature" in title.lower() or "hottest" in title.lower() or "weather" in title.lower():
        active_subs = [m for m in ev.get("markets", []) if not m.get("closed", False)]
        if active_subs:
            upcoming_weather.append((ev.get("volume", 0), ev.get("volume24hr", 0), ev, active_subs))

upcoming_weather.sort(key=lambda x: x[0], reverse=True)

for vol, vol24, ev, subs in upcoming_weather[:15]:
    print(f"\n{ev['title']} | Vol: ${vol:,.2f} (24h: ${vol24:,.2f})")
    print(f"URL: https://polymarket.com/event/{ev['slug']}")
    for s in subs[:5]:
        print(f"  - {s.get('question')} | Prices: {s.get('outcomePrices')} | End: {s.get('endDate')}")
    if len(subs) > 5:
        print(f"  ... and {len(subs) - 5} more brackets")
