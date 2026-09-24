import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open("polymarket_climate_energy_analysis.json", "r", encoding="utf-8") as f:
    events = json.load(f)

print(f"Total events analyzed: {len(events)}")

# Filter to active events with volume > $1,000 or recent 24h activity
relevant = []
for ev in events:
    if ev.get("closed"):
        continue
    # check active submarkets
    active_subs = ev.get("active_submarkets", [])
    if not active_subs:
        continue
    vol = ev.get("volume", 0)
    vol24 = ev.get("volume24hr", 0)
    relevant.append((vol, vol24, ev))

relevant.sort(key=lambda x: (x[1], x[0]), reverse=True)

print(f"\n--- TOP ACTIVE MARKETS BY VOLUME/ACTIVITY ({len(relevant)} found) ---\n")
for vol, vol24, ev in relevant[:20]:
    print(f"★ [{ev['title']}]")
    print(f"  URL: https://polymarket.com/event/{ev['slug']}")
    print(f"  Total Vol: ${vol:,.2f} | 24h Vol: ${vol24:,.2f}")
    for m in ev.get("active_submarkets", []):
        q = m.get("question")
        outcomes = m.get("outcomes")
        prices = m.get("outcomePrices")
        end = m.get("endDate")
        print(f"    -> {q}")
        print(f"       Prices: {prices} | Outcomes: {outcomes} | End: {end}")
    print()
