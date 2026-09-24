import json

with open("polymarket_climate_energy_analysis.json", "r", encoding="utf-8") as f:
    events = json.load(f)

for ev in events:
    if "madrid" in ev["slug"]:
        print("Title:", ev["title"])
        print("Description:", ev.get("description", ""))
        markets = ev.get("markets", [])
        if markets:
            print("Market Description:", markets[0].get("description", ""))
            print("Resolution Source:", markets[0].get("resolutionSource", ""))
        break

for ev in events:
    if "hottest-year" in ev["slug"]:
        print("\n--- Hottest Year ---")
        print("Title:", ev["title"])
        print("Description:", ev.get("description", ""))
        markets = ev.get("markets", [])
        if markets:
            print("Market Description:", markets[0].get("description", ""))
            print("Resolution Source:", markets[0].get("resolutionSource", ""))
        break
