import urllib.request
import json
from datetime import datetime, timezone

print("=== 1. TESTANDO API METAR (NOAA AVIATION WEATHER) ===")
# KJFK: New York JFK
# KLGA: New York LaGuardia
# KORD: Chicago O'Hare
# KMIA: Miami Int'l
# KAUS: Austin Bergstrom
# KIAH: Houston George Bush
metar_url = "https://aviationweather.gov/api/data/metar?ids=KJFK,KLGA,KORD,KMIA,KAUS,KIAH&format=json"
req = urllib.request.Request(metar_url, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        print(f"METAR reports recebidos: {len(data)}")
        for item in data:
            c = item.get("temp")
            f = round(c * 9/5 + 32, 1) if c is not None else None
            station = item.get("icaoId")
            rep_time = item.get("reportTime")
            print(f"  Aeroporto: {station} | Report: {rep_time} | Temp: {c} C ({f} F)")
except Exception as e:
    print(f"Erro METAR: {e}")

print("\n=== 2. TESTANDO MERCADOS DE TEMPERATURA NA KALSHI ===")
kalshi_url = "https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=200"
req2 = urllib.request.Request(kalshi_url, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req2, timeout=15) as resp:
        m_data = json.loads(resp.read().decode()).get("markets", [])
        temp_markets = []
        for m in m_data:
            ticker = m.get("ticker", "")
            title = m.get("title", "").lower()
            category = m.get("category", "").lower()
            rules = m.get("rules_primary", "").lower()
            if any(k in ticker for k in ["HIGHNY", "HIGHAUS", "HIGHCHI", "HIGHMIA", "HIGHMOU", "HIGHPHIL"]) or "temperature" in title or "high temp" in title:
                temp_markets.append(m)
        
        print(f"Mercados de Temperatura abertos encontrados na Kalshi: {len(temp_markets)}")
        for m in temp_markets[:10]:
            print(f"  Ticker: {m.get('ticker')} | Título: {m.get('title')} | Yes Ask: {m.get('yes_ask_dollars')} | No Ask: {m.get('no_ask_dollars')}")
except Exception as e:
    print(f"Erro Kalshi: {e}")
